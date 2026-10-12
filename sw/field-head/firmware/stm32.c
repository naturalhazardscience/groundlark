/* SPDX-License-Identifier: MIT */
#include "head.h"
#include "boot.h"
#include <libopencm3/cm3/cortex.h>
#include <libopencm3/cm3/systick.h>
#include <libopencm3/cm3/nvic.h>
#include <libopencm3/stm32/rcc.h>
#include <libopencm3/stm32/crs.h>
#include <libopencm3/stm32/gpio.h>
#include <libopencm3/stm32/i2c.h>
#include <libopencm3/stm32/flash.h>
#include <libopencm3/stm32/iwdg.h>
#include <libopencm3/stm32/syscfg.h>
#include <libopencm3/stm32/timer.h>
#include <libopencm3/stm32/exti.h>
#include <libopencm3/usb/usbd.h>
#include <libopencm3/usb/cdc.h>
#include <string.h>
#ifndef BH_USB_VID
#define BH_USB_VID 0x1209
#define BH_USB_PID 0x0001
#endif
static bh_state state;
static usbd_device *usb;
static volatile uint64_t milliseconds;
static bool configured,dtr,suspended,tx_busy,zlp_pending;
static uint16_t tx_offset;
static volatile uint8_t ready_mask;
static volatile uint64_t ready_us[4];
static volatile bool ready_armed;
static bool spi_enabled;
#define MAG_INPUTS (GPIO4|GPIO5|GPIO6|GPIO7)
#define MAG_OUTPUTS (GPIO1|GPIO2|GPIO3)
#define MAG_READY (GPIO0|GPIO1|GPIO3|GPIO4)
uint64_t bh_micros(void){
    static uint32_t previous;static uint64_t high;
    uint32_t mask=cm_mask_interrupts(1),low=timer_get_counter(TIM2);
    if(low<previous)high+=1ull<<32;previous=low;
    uint64_t result=high+low;cm_mask_interrupts(mask);return result;
}
void sys_tick_handler(void){milliseconds++;(void)bh_micros();}
uint64_t bh_clock(void){uint32_t mask=cm_mask_interrupts(1);uint64_t t=milliseconds;cm_mask_interrupts(mask);return t;}
void bh_delay(uint32_t ms){uint64_t end=bh_clock()+ms;while(bh_clock()<end)if(usb)usbd_poll(usb);}
static void ready_interrupt(void){
    const uint32_t lines[]={EXTI0,EXTI1,EXTI3,EXTI4};uint64_t stamp=bh_micros();
    for(unsigned i=0;i<4;i++)if(exti_get_flag_status(lines[i])){
        exti_reset_request(lines[i]);
        if(ready_armed&&!(ready_mask&(1u<<i))){ready_us[i]=stamp;ready_mask|=1u<<i;}
    }
}
void exti0_1_isr(void){ready_interrupt();}
void exti2_3_isr(void){ready_interrupt();}
void exti4_15_isr(void){ready_interrupt();}
bool bh_ready_arm(void){
    uint32_t mask=cm_mask_interrupts(1);ready_armed=false;ready_mask=0;
    exti_reset_request(MAG_READY);bool low=!(gpio_get(GPIOB,MAG_READY));
    if(low){ready_armed=true;exti_enable_request(MAG_READY);}
    cm_mask_interrupts(mask);return low;
}
uint8_t bh_ready(uint64_t observed_us[4]){
    uint32_t mask=cm_mask_interrupts(1);uint8_t result=ready_mask;
    for(unsigned i=0;i<4;i++)observed_us[i]=ready_us[i];
    cm_mask_interrupts(mask);return result;
}
/* Conservative mode-0 software SPI. All four SO bits are captured in one
 * GPIO read; interrupts may stretch clocks but cannot offset the shared edge.
 * Actual edge shape, timing and DRDY latency still require bench qualification. */
static void spi_wait(void){uint32_t start=timer_get_counter(TIM2);while((uint32_t)(timer_get_counter(TIM2)-start)<2){}}
static void spi_byte(uint8_t value,uint8_t read[4]){
    for(unsigned bit=0;bit<8;bit++){
        if(value&0x80)gpio_set(GPIOA,GPIO2);else gpio_clear(GPIOA,GPIO2);value<<=1;
        spi_wait();gpio_set(GPIOA,GPIO1);spi_wait();uint32_t lanes=GPIO_IDR(GPIOA);
        if(read)for(unsigned i=0;i<4;i++)read[i]=(uint8_t)((read[i]<<1)|((lanes>>(4+i))&1));
        gpio_clear(GPIOA,GPIO1);
    }
}
bool bh_spi(uint8_t reg,const uint8_t *write,size_t n,uint8_t read[4][9]){
    if(!state.powered||n>9||!n||(!write&&!read)||(write&&read))return false;
    /* First transaction occurs only after head.c's 20 ms rail-settle interval.
     * Leave all push-pull signals high impedance throughout the supply ramp. */
    if(!spi_enabled){
        gpio_set(GPIOA,GPIO3);gpio_clear(GPIOA,GPIO1|GPIO2);
        gpio_mode_setup(GPIOA,GPIO_MODE_OUTPUT,GPIO_PUPD_NONE,MAG_OUTPUTS);
        gpio_set_output_options(GPIOA,GPIO_OTYPE_PP,GPIO_OSPEED_2MHZ,MAG_OUTPUTS);
        gpio_mode_setup(GPIOA,GPIO_MODE_INPUT,GPIO_PUPD_NONE,MAG_INPUTS);
        gpio_mode_setup(GPIOB,GPIO_MODE_INPUT,GPIO_PUPD_NONE,MAG_READY);spi_enabled=true;
    }
    gpio_clear(GPIOA,GPIO3);spi_wait();spi_byte(reg|(read?0x80:0),0);
    for(size_t j=0;j<n;j++){
        uint8_t lanes[4]={0};spi_byte(write?write[j]:0,read?lanes:0);
        if(read)for(unsigned i=0;i<4;i++)read[i][j]=lanes[i];
    }
    spi_wait();gpio_set(GPIOA,GPIO3);gpio_clear(GPIOA,GPIO2);return true;
}
void bh_power(bool enabled){
    ready_armed=false;ready_mask=0;exti_disable_request(MAG_READY);exti_reset_request(MAG_READY);
    spi_enabled=false;gpio_mode_setup(GPIOA,GPIO_MODE_ANALOG,GPIO_PUPD_NONE,MAG_INPUTS|MAG_OUTPUTS);
    gpio_mode_setup(GPIOB,GPIO_MODE_ANALOG,GPIO_PUPD_NONE,MAG_READY);
    if(enabled){
        gpio_set(GPIOA,GPIO0);
        gpio_mode_setup(GPIOB,GPIO_MODE_AF,GPIO_PUPD_NONE,GPIO6|GPIO7);gpio_set_af(GPIOB,GPIO_AF1,GPIO6|GPIO7);gpio_set_output_options(GPIOB,GPIO_OTYPE_OD,GPIO_OSPEED_2MHZ,GPIO6|GPIO7);i2c_peripheral_enable(I2C1);
    }else{
        i2c_peripheral_disable(I2C1);gpio_mode_setup(GPIOB,GPIO_MODE_ANALOG,GPIO_PUPD_NONE,MAG_READY|GPIO6|GPIO7);
        gpio_mode_setup(GPIOA,GPIO_MODE_ANALOG,GPIO_PUPD_NONE,MAG_INPUTS|MAG_OUTPUTS);gpio_clear(GPIOA,GPIO0);
    }
}
static bool wait_flag(uint32_t flag,uint64_t end){
    for(unsigned spin=0;spin<100000;spin++){
        uint32_t flags=I2C_ISR(I2C1);
        if(flags&(I2C_ISR_NACKF|I2C_ISR_ARLO))return false;
        if(flags&I2C_ISR_BERR)I2C_ICR(I2C1)=I2C_ICR_BERRCF;
        if(flags&flag)return true;
        if(bh_clock()>=end)return false;
        if(usb)usbd_poll(usb);
    }return false;
}
bool bh_i2c(uint8_t addr,const uint8_t *w,size_t wn,uint8_t *r,size_t rn){
    if(wn>32||rn>32||(!wn&&!rn)||!state.powered)return false;
    uint64_t end=bh_clock()+5;bool ok=true;
    for(unsigned spin=0;i2c_busy(I2C1);spin++)if(spin>=100000||bh_clock()>=end){ok=false;break;}
    I2C_ICR(I2C1)=0x3f38;
    if(ok&&wn){I2C_CR2(I2C1)=((uint32_t)addr<<1)|((uint32_t)wn<<16)|I2C_CR2_START|(rn?0:I2C_CR2_AUTOEND);
        for(size_t i=0;i<wn&&ok;i++){ok=wait_flag(I2C_ISR_TXIS,end);if(ok)I2C_TXDR(I2C1)=w[i];}
        if(ok)ok=wait_flag(rn?I2C_ISR_TC:I2C_ISR_STOPF,end);}
    if(ok&&rn){I2C_CR2(I2C1)=((uint32_t)addr<<1)|((uint32_t)rn<<16)|I2C_CR2_RD_WRN|I2C_CR2_START|I2C_CR2_AUTOEND;
        for(size_t i=0;i<rn&&ok;i++){ok=wait_flag(I2C_ISR_RXNE,end);if(ok)r[i]=(uint8_t)I2C_RXDR(I2C1);}
        if(ok)ok=wait_flag(I2C_ISR_STOPF,end);}
    if(!ok){I2C_CR2(I2C1)|=I2C_CR2_STOP;i2c_peripheral_disable(I2C1);if(state.powered)i2c_peripheral_enable(I2C1);}
    I2C_ICR(I2C1)=0x3f38;return ok&&state.powered;
}
static const struct usb_device_descriptor device={
    .bLength=USB_DT_DEVICE_SIZE,.bDescriptorType=USB_DT_DEVICE,.bcdUSB=0x0200,
    .bDeviceClass=USB_CLASS_CDC,.bMaxPacketSize0=64,.idVendor=BH_USB_VID,
    .idProduct=BH_USB_PID,.bcdDevice=0x0100,.iManufacturer=1,.iProduct=2,.iSerialNumber=3,.bNumConfigurations=1};
static const struct usb_endpoint_descriptor comm_ep[]={
    {.bLength=USB_DT_ENDPOINT_SIZE,.bDescriptorType=USB_DT_ENDPOINT,.bEndpointAddress=0x83,.bmAttributes=USB_ENDPOINT_ATTR_INTERRUPT,.wMaxPacketSize=16,.bInterval=255}};
static const struct usb_endpoint_descriptor data_ep[]={
    {.bLength=USB_DT_ENDPOINT_SIZE,.bDescriptorType=USB_DT_ENDPOINT,.bEndpointAddress=0x01,.bmAttributes=USB_ENDPOINT_ATTR_BULK,.wMaxPacketSize=64},
    {.bLength=USB_DT_ENDPOINT_SIZE,.bDescriptorType=USB_DT_ENDPOINT,.bEndpointAddress=0x82,.bmAttributes=USB_ENDPOINT_ATTR_BULK,.wMaxPacketSize=64}};
static const struct {
    struct usb_cdc_header_descriptor header;
    struct usb_cdc_call_management_descriptor call;
    struct usb_cdc_acm_descriptor acm;
    struct usb_cdc_union_descriptor group;
} __attribute__((packed)) extra={
    {5,CS_INTERFACE,USB_CDC_TYPE_HEADER,0x0110},
    {5,CS_INTERFACE,USB_CDC_TYPE_CALL_MANAGEMENT,0,1},
    {4,CS_INTERFACE,USB_CDC_TYPE_ACM,2},
    {5,CS_INTERFACE,USB_CDC_TYPE_UNION,0,1}};
static const struct usb_interface_descriptor interfaces[]={
    {.bLength=USB_DT_INTERFACE_SIZE,.bDescriptorType=USB_DT_INTERFACE,.bInterfaceNumber=0,.bNumEndpoints=1,.bInterfaceClass=USB_CLASS_CDC,.bInterfaceSubClass=USB_CDC_SUBCLASS_ACM,.bInterfaceProtocol=USB_CDC_PROTOCOL_AT,.endpoint=comm_ep,.extra=&extra,.extralen=sizeof extra},
    {.bLength=USB_DT_INTERFACE_SIZE,.bDescriptorType=USB_DT_INTERFACE,.bInterfaceNumber=1,.bNumEndpoints=2,.bInterfaceClass=USB_CLASS_DATA,.endpoint=data_ep}};
static const struct usb_interface ifaces[]={{.num_altsetting=1,.altsetting=interfaces},{.num_altsetting=1,.altsetting=interfaces+1}};
static const struct usb_config_descriptor configuration={
    .bLength=USB_DT_CONFIGURATION_SIZE,.bDescriptorType=USB_DT_CONFIGURATION,.bNumInterfaces=2,.bConfigurationValue=1,.bmAttributes=0x80,.bMaxPower=50,.interface=ifaces};
static uint8_t control_buffer[128];
static struct usb_cdc_line_coding coding={115200,0,0,8};
static enum usbd_request_return_codes control(usbd_device *dev,struct usb_setup_data *req,uint8_t **buf,uint16_t *len,void (**complete)(usbd_device *,struct usb_setup_data *)) {
    (void)dev;(void)complete;
    if(req->wIndex!=0)return USBD_REQ_NOTSUPP;
    if(req->bRequest==USB_CDC_REQ_SET_CONTROL_LINE_STATE) { dtr=(req->wValue&1)!=0;return USBD_REQ_HANDLED; }
    if(req->bRequest==USB_CDC_REQ_GET_LINE_CODING) { *buf=(uint8_t *)&coding;*len=sizeof coding;return USBD_REQ_HANDLED; }
    if(req->bRequest==USB_CDC_REQ_SET_LINE_CODING && *len==sizeof coding) { memcpy(&coding,*buf,sizeof coding);return USBD_REQ_HANDLED; }
    return USBD_REQ_NOTSUPP;
}
static void receive(usbd_device *dev,uint8_t ep) { uint8_t ignored[64];usbd_ep_read_packet(dev,ep,ignored,sizeof ignored); }
static void transmitted(usbd_device *dev,uint8_t ep) { (void)dev;(void)ep;tx_busy=false; }
static void set_config(usbd_device *dev,uint16_t value) {
    configured=value==1;
    if(!configured)return;
    usbd_ep_setup(dev,0x01,USB_ENDPOINT_ATTR_BULK,64,receive);
    tx_busy=false;zlp_pending=false;
    usbd_ep_setup(dev,0x82,USB_ENDPOINT_ATTR_BULK,64,transmitted);
    usbd_ep_setup(dev,0x83,USB_ENDPOINT_ATTR_INTERRUPT,16,NULL);
    usbd_register_control_callback(dev,USB_REQ_TYPE_CLASS|USB_REQ_TYPE_INTERFACE,USB_REQ_TYPE_TYPE|USB_REQ_TYPE_RECIPIENT,control);
}
static void reset_usb(void) { configured=false;dtr=false;suspended=false;tx_busy=false;zlp_pending=false;tx_offset=0;bh_supply(&state,false,bh_clock()); }
static void suspend_usb(void) { suspended=true;tx_offset=0;bh_supply(&state,false,bh_clock()); }
static void resume_usb(void) { suspended=false; }

static void boot_erase(unsigned page){flash_erase_page(0x08007800+page*1024);}
static void boot_program(unsigned word,uint32_t value){flash_program_word(0x08007800+word*4,value);}
int main(void){
    rcc_clock_setup_in_hsi48_out_48mhz();rcc_set_usbclk_source(RCC_HSI48);
    rcc_periph_clock_enable(RCC_GPIOA);rcc_periph_clock_enable(RCC_GPIOB);
    gpio_mode_setup(GPIOA,GPIO_MODE_ANALOG,GPIO_PUPD_NONE,GPIO1|GPIO2|GPIO3|GPIO4|GPIO5|GPIO6|GPIO7|GPIO8|GPIO15);
    gpio_mode_setup(GPIOB,GPIO_MODE_ANALOG,GPIO_PUPD_NONE,GPIO0|GPIO1|GPIO3|GPIO4|GPIO5|GPIO6|GPIO7);
    gpio_clear(GPIOA,GPIO0);gpio_mode_setup(GPIOA,GPIO_MODE_OUTPUT,GPIO_PUPD_NONE,GPIO0);
    rcc_periph_clock_enable(RCC_TIM2);timer_set_prescaler(TIM2,47);timer_set_period(TIM2,0xffffffff);timer_generate_event(TIM2,TIM_EGR_UG);timer_enable_counter(TIM2);
    rcc_periph_clock_enable(RCC_SYSCFG_COMP);
    exti_select_source(EXTI0,GPIOB);exti_select_source(EXTI1,GPIOB);exti_select_source(EXTI3,GPIOB);exti_select_source(EXTI4,GPIOB);
    exti_set_trigger(MAG_READY,EXTI_TRIGGER_RISING);
    nvic_enable_irq(NVIC_EXTI0_1_IRQ);nvic_enable_irq(NVIC_EXTI2_3_IRQ);nvic_enable_irq(NVIC_EXTI4_15_IRQ);
    systick_set_clocksource(STK_CSR_CLKSOURCE_AHB);systick_set_reload(47999);systick_interrupt_enable();systick_counter_enable();
    rcc_periph_clock_enable(RCC_I2C1);rcc_set_i2c_clock_hsi(RCC_I2C1);rcc_osc_on(RCC_HSI);rcc_wait_for_osc_ready(RCC_HSI);
    i2c_set_speed(I2C1,i2c_speed_sm_100k,8);
    char serial[25];const uint8_t *uid=(const uint8_t *)0x1ffff7ac;static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<12;i++){serial[2*i]=hex[uid[i]>>4];serial[2*i+1]=hex[uid[i]&15];}serial[24]=0;
    flash_unlock();flash_clear_status_flags();uint32_t boot=sk_boot_next((const volatile uint32_t *)0x08007800,boot_erase,boot_program);flash_lock();
    bh_init(&state,serial,boot);
    const char *strings[]={"Groundlark","Burrowlark DAQUSB-01 prototype",serial};
    rcc_periph_clock_enable(RCC_CRS);crs_autotrim_usb_enable();rcc_periph_clock_enable(RCC_USB);rcc_periph_clock_enable(RCC_SYSCFG_COMP);
    /* STM32F042K6 pins 21/22: map USB PA11/12 onto PA9/10. RM0091 CFGR1 bit 4. */
    SYSCFG_CFGR1|=(1u<<4);
    gpio_mode_setup(GPIOA,GPIO_MODE_AF,GPIO_PUPD_NONE,GPIO9|GPIO10);gpio_set_af(GPIOA,GPIO_AF2,GPIO9|GPIO10);
    usb=usbd_init(&st_usbfs_v2_usb_driver,&device,&configuration,strings,3,control_buffer,sizeof control_buffer);
    usbd_register_set_config_callback(usb,set_config);usbd_register_reset_callback(usb,reset_usb);usbd_register_suspend_callback(usb,suspend_usb);usbd_register_resume_callback(usb,resume_usb);
    iwdg_set_period_ms(2000);iwdg_start();
    for(;;){
        usbd_poll(usb);bh_supply(&state,configured&&!suspended,bh_clock());
        bool connected=configured&&!suspended&&dtr;
        if(connected!=state.connected){tx_offset=0;bh_connection(&state,connected);}
        bh_tick(&state,bh_clock());
        uint16_t len;const uint8_t *frame=bh_tx(&state,&len);
        if(connected&&!tx_busy&&zlp_pending){tx_busy=true;zlp_pending=false;usbd_ep_write_packet(usb,0x82,NULL,0);}
        else if(frame&&connected&&!tx_busy){unsigned remain=len-tx_offset,n=remain>64?64:remain;int sent=usbd_ep_write_packet(usb,0x82,frame+tx_offset,n);
            if(sent>0){tx_busy=true;tx_offset+=(uint16_t)sent;if(tx_offset==len){bh_tx_done(&state);tx_offset=0;zlp_pending=sent==64;}}}
        iwdg_reset();__asm__("wfi");
    }
}
