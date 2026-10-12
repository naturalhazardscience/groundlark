/* SPDX-License-Identifier: MIT
 * Burrowlark common-trigger 10 Hz four-RM3100 / 1 Hz SHT45 profile. No heap or RTOS.
 * PNI RM3100 breakout manual r08; Sensirion SHT4x high-precision command.
 */
#include "head.h"
#include <string.h>
typedef struct { uint8_t d[192];unsigned n;bool bad; } buf;
static void byte(buf *b,uint8_t v) { if(b->n<sizeof b->d)b->d[b->n++]=v;else b->bad=true; }
static void var(buf *b,uint64_t v) { while(v>127){byte(b,(uint8_t)v|128);v>>=7;}byte(b,(uint8_t)v); }
static void num(buf *b,unsigned f,uint64_t v) { var(b,f<<3);var(b,v); }
static void bytes(buf *b,unsigned f,const void *data,unsigned n) { var(b,(f<<3)|2);var(b,n);const uint8_t *p=data;for(unsigned i=0;i<n;i++)byte(b,p[i]); }
static void sub(buf *b,unsigned f,const buf *v) { bytes(b,f,v->d,v->n);b->bad|=v->bad; }
static bool enqueue(bh_state *s,unsigned field,const buf *body) {
    if(s->count==BH_QUEUE){if(field==12)s->overflow=true;return false;}
    if(body->bad || !s->connected || !s->boot)return false;
    buf b={0};num(&b,1,1);bytes(&b,2,s->device,(unsigned)strlen(s->device));
    byte(&b,25);for(unsigned i=0;i<8;i++)byte(&b,(uint8_t)(s->boot>>(i*8)));sub(&b,field,body);
    uint32_t crc=~0u;for(unsigned i=0;i<b.n;i++){crc^=b.d[i];for(unsigned j=0;j<8;j++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1)));}
    crc=~crc;for(unsigned i=0;i<4;i++)byte(&b,(uint8_t)(crc>>(i*8)));if(b.bad)return false;
    unsigned slot=(s->head+s->count)%BH_QUEUE;uint8_t *out=s->frames[slot];unsigned n=1,start=0;uint8_t code=1;
    if(field==10){out[0]=0;start=1;n=2;}
    for(unsigned i=0;i<b.n;i++) {
        if(!b.d[i]){out[start]=code;start=n++;code=1;}
        else{out[n++]=b.d[i];if(++code==255){out[start]=code;start=n++;code=1;}}
    }
    out[start]=code;out[n++]=0;s->lengths[slot]=(uint16_t)n;s->count++;return true;
}
static uint8_t crc8(const uint8_t *p){uint8_t c=255;for(unsigned i=0;i<2;i++){c^=p[i];for(unsigned j=0;j<8;j++)c=(uint8_t)((c<<1)^((c&128)?0x31:0));}return c;}
static uint8_t configure(void){
    uint8_t data[4][9],cycles[]={0,200,0,200,0,200},stop=0,reset=0x94,enabled=0;
    bool ok=bh_spi(1,&stop,1,0) && bh_spi(4,cycles,6,0) && bh_spi(4,0,6,data);
    if(ok)for(unsigned i=0;i<4;i++)if(memcmp(data[i],cycles,6))ok=false;
    if(ok)enabled=15;
    if(bh_i2c(0x44,&reset,1,0,0)){bh_delay(1);enabled|=16;}
    return enabled;
}
void bh_init(bh_state *s,const char *device,uint64_t boot){memset(s,0,sizeof *s);size_t n=strlen(device);if(!n||n>32)return;memcpy(s->device,device,n);s->boot=boot;bh_power(false);}
void bh_supply(bh_state *s,bool enabled,uint64_t ms){
    if(enabled==s->powered)return;
    s->power_generation++;s->powered=enabled;s->initialized=false;s->enabled=0;s->ready=ms+20;
    s->measuring=false;s->mag_fault=false;s->trigger_us=0;
    memset(s->failures,0,sizeof s->failures);
    if(!enabled)bh_connection(s,false);
    bh_power(enabled);
}
void bh_connection(bh_state *s,bool connected){
    connected=connected&&s->powered&&s->boot;
    if(connected==s->connected)return;
    s->connected=connected;s->count=s->head=0;s->announce=0;
    if(connected&&s->initialized){if(s->revision==UINT32_MAX){s->boot=0;return;}s->revision++;s->announce=1;}
}
static const unsigned ids[]={7,18,19,20,17};
static bool handshake(bh_state *s){
    buf b={0};
    if(s->announce==1){num(&b,1,2);bytes(&b,2,"burrowlark-0.2.0",15);uint8_t list[]={7,18,19,20,17};bytes(&b,3,list,5);if(!enqueue(s,10,&b))return false;s->announce=2;}
    else{
        num(&b,1,s->revision);
        for(unsigned i=0;i<5;i++){buf c={0};num(&c,1,ids[i]);num(&c,2,(s->enabled>>i)&1);num(&c,3,(s->enabled&(1u<<i))?(i==4?1000000000:100000000):0);
            if(i<4){num(&c,8,200);num(&c,9,200);num(&c,10,200);}sub(&b,2,&c);}
        if(!enqueue(s,11,&b))return false;s->announce=0;
    }return true;
}
static void status(bh_state *s,unsigned sensor,const char *detail){buf b={0};num(&b,1,sensor);num(&b,2,3);bytes(&b,4,detail,(unsigned)strlen(detail));enqueue(s,13,&b);}
static void sample(bh_state *s,unsigned index,uint64_t us,unsigned quality,const uint8_t *raw,uint64_t ready_us){
    buf batch={0},sample={0},stamp={0};num(&batch,1,ids[index]);num(&batch,2,s->revision);
    num(&sample,1,s->sequence[index]);num(&stamp,1,2);num(&stamp,2,us*1000);sub(&sample,2,&stamp);num(&sample,3,quality);
    if(index<4){buf timing={0};num(&timing,1,s->sequence[index]);if(s->trigger_us)num(&timing,2,s->trigger_us*1000);if(ready_us)num(&timing,3,ready_us*1000);sub(&sample,21,&timing);}
    if(quality==1||quality==3){buf payload={0};
        if(index==4)bytes(&payload,1,raw,6);
        else{buf xyz={0};for(unsigned i=0;i<3;i++){uint32_t u=(uint32_t)raw[3*i]<<16|(uint32_t)raw[3*i+1]<<8|raw[3*i+2];int32_t v=(int32_t)(u&0x800000?u|0xff000000:u);num(&xyz,i+1,((uint32_t)v<<1)^(uint32_t)(v>>31));}sub(&payload,1,&xyz);}
        sub(&sample,index==4?18:12,&payload);
    }
    sub(&batch,3,&sample);enqueue(s,12,&batch); /* Physical conversion loss stays unknown. */
}
static bool advance(bh_state *s,unsigned first,unsigned end,uint64_t skipped){
    for(unsigned i=first;i<end;i++){
        if(s->sequence[i]>UINT64_MAX-skipped-1){s->boot=0;return false;}
        s->sequence[i]+=skipped;
    }return true;
}
void bh_tick(bh_state *s,uint64_t ms){
    if(!s->powered||!s->boot)return;
    uint32_t generation=s->power_generation;
    if(!s->initialized){if(ms<s->ready)return;uint8_t enabled=configure();
        if(!s->powered||generation!=s->power_generation)return;
        s->enabled=enabled;s->initialized=true;s->next[0]=s->next[1]=bh_clock();
        if(s->revision==UINT32_MAX){s->boot=0;return;}s->revision++;if(s->connected)s->announce=1;}
    while(s->announce){if(!handshake(s))return;}
    if(s->overflow&&s->count<BH_QUEUE&&s->connected){
        buf b={0};num(&b,1,0);num(&b,2,4);bytes(&b,4,"USB sample queue overflow",25);
        if(enqueue(s,13,&b))s->overflow=false;
    }
    uint64_t now=bh_clock();
    if((s->enabled&15)==15&&!s->measuring&&now>=s->next[0]){
        if(!advance(s,0,4,(now-s->next[0])/100))return;
        s->next[0]=now+100;s->trigger_us=0;
        uint8_t drain[4][9],poll=0x70;
        /* Clear old DRDY by reading all results, then require all lines LOW.
         * A timeout latches until a power cycle: no late result can enter a new cohort. */
        if(!s->mag_fault){
            if(bh_spi(0x24,0,9,drain)&&bh_ready_arm()&&bh_spi(0,&poll,1,0))s->trigger_us=bh_micros();
            else{s->mag_fault=true;status(s,0,"magnetic array trigger fault; power cycle required");}
        }
        if(!s->powered||generation!=s->power_generation)return;
        s->measuring=true;
    }
    if(s->measuring){
        uint64_t observed[4]={0};uint8_t mask=s->trigger_us?bh_ready(observed):0;
        if(s->mag_fault||mask==15||bh_micros()-s->trigger_us>=50000){
            uint8_t raw[4][9]={{0}},flags[4][9]={{0}};
            for(unsigned i=0;i<4;i++)if(observed[i]<s->trigger_us||observed[i]-s->trigger_us>50000)mask&=(uint8_t)~(1u<<i);
            bool ok=!s->mag_fault&&bh_spi(0x34,0,1,flags)&&bh_spi(0x24,0,9,raw);
            if(!s->powered||generation!=s->power_generation)return;
            for(unsigned i=0;i<4;i++)if(!(flags[i][0]&0x80))mask&=(uint8_t)~(1u<<i);
            if(!ok||mask!=15){s->mag_fault=true;status(s,0,"magnetic array timeout; power cycle required");}
            /* Reserve the entire quartet. A congested USB link drops all four. */
            bool room=s->count<=BH_QUEUE-4;
            if(!room&&s->connected)s->overflow=true;
            for(unsigned i=0;i<4;i++){
                unsigned quality=ok&&(mask&(1u<<i))&&(flags[i][0]&0x80)?1:2;
                if(quality==1)for(unsigned j=0;j<3;j++)if((raw[i][j*3]==0x80&&!raw[i][j*3+1]&&!raw[i][j*3+2])||(raw[i][j*3]==0x7f&&raw[i][j*3+1]==255&&raw[i][j*3+2]==255))quality=3;
                if(room)sample(s,i,bh_micros(),quality,raw[i],(mask&(1u<<i))?observed[i]:0);
                s->sequence[i]++;
            }
            s->measuring=false;
        }
    }
    /* Climate I/O only between magnetic integrations; it never delays DRDY handling. */
    now=bh_clock();
    if(!s->measuring&&(s->enabled&16)&&now>=s->next[1]){
        if(!advance(s,4,5,(now-s->next[1])/1000))return;
        s->next[1]=now+1000;uint8_t raw[6]={0},command=0xfd;unsigned quality=2;
        if(s->failures[4]<3&&bh_i2c(0x44,&command,1,0,0)){
            bh_delay(9);
            if(s->powered&&generation==s->power_generation&&bh_i2c(0x44,0,0,raw,6)&&crc8(raw)==raw[2]&&crc8(raw+3)==raw[5])quality=1;
        }
        if(!s->powered||generation!=s->power_generation)return;
        if(quality==2&&s->failures[4]<3){s->failures[4]++;status(s,17,"sensor read failed");}
        if(quality==1)s->failures[4]=0;
        sample(s,4,bh_micros(),quality,raw,0);s->sequence[4]++;
    }
}
const uint8_t *bh_tx(bh_state *s,uint16_t *length){if(!s->count)return 0;*length=s->lengths[s->head];return s->frames[s->head];}
void bh_tx_done(bh_state *s){if(s->count){s->head=(s->head+1)%BH_QUEUE;s->count--;}}
