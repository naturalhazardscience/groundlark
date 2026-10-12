/* SPDX-License-Identifier: MIT */
#include "head.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint64_t now;static bool power;static unsigned mode;static uint8_t registers[256];
static uint64_t climate_ready,trigger,power_on;static bool armed;static uint8_t seen;static unsigned polls;
static bh_state *current;
uint64_t bh_clock(void){return now;}
uint64_t bh_micros(void){return now*1000;}
void bh_delay(uint32_t ms){now+=ms;if(mode==6&&power)bh_supply(current,false,now);}
void bh_power(bool enabled){power=enabled;power_on=now;armed=false;seen=0;trigger=0;}
bool bh_ready_arm(void){assert(power);seen=0;armed=true;return mode!=9;}
uint8_t bh_ready(uint64_t times[4]){
    /* Four independent conversion clocks, not a shared ready callback. */
    const unsigned delays[]={12500,12720,12910,12630};
    for(unsigned i=0;i<4;i++){
        uint64_t done=trigger+delays[i]+((mode==8&&i==3)?2500:0)+((mode==12&&i==3)?70000:0);
        if(mode==7&&i==2)continue;
        if(armed&&bh_micros()>=done){seen|=1u<<i;times[i]=done;}
    }return seen;
}
bool bh_spi(uint8_t reg,const uint8_t *w,size_t n,uint8_t r[4][9]){
    assert(power&&n<=9&&now>=power_on+20);
    if(mode==1&&now>500)return false;
    if(w){
        memcpy(registers+reg,w,n);
        if(reg==0){assert(armed&&w[0]==0x70);trigger=bh_micros();polls++;}
        return true;
    }
    for(unsigned i=0;i<4;i++){
        if(reg==0x34){r[i][0]=(seen&(1u<<i))?0x80:0;if(mode==11&&i==1)r[i][0]=0;}
        else if(reg==0x24){
            const uint8_t v[]={0xff,0xff,0xfe,0,0,0,0x7f,0xff,0xfe};assert(n==9);memcpy(r[i],v,9);
            r[i][5]=(uint8_t)i; /* Independently distinguish SO lanes. */
            if(mode==13&&i==0){r[i][0]=0x7f;r[i][1]=r[i][2]=0xff;}
            if(mode==13&&i==3){r[i][6]=0x80;r[i][7]=r[i][8]=0;}
        }else memcpy(r[i],registers+reg,n);
        if(mode==10&&reg==4&&i==3)r[i][5]^=1;
    }
    if(reg==0x24)armed=false;
    return true;
}
bool bh_i2c(uint8_t addr,const uint8_t *w,size_t wn,uint8_t *r,size_t rn){
    assert(power);
    if(mode==1&&now>500)return false;
    assert(addr==0x44);
    if(wn){assert(wn==1&&(w[0]==0xfd||w[0]==0x94));if(w[0]==0xfd)climate_ready=now+9;return true;}
    assert(rn==6&&now>=climate_ready);
    const uint8_t v[]={0x66,0x66,0x93,0x80,0,0xa2};memcpy(r,v,6);if(mode==2)r[2]^=1;return true;
}
static void drain(bh_state *s){uint16_t length;const uint8_t *p;while((p=bh_tx(s,&length))){assert(length<=BH_FRAME_MAX);fwrite(p,1,length,stdout);bh_tx_done(s);}}
int main(int argc,char **argv){
    mode=argc>1?(unsigned)atoi(argv[1]):0;
    bh_state s;current=&s;
    if(mode==14)now=1000000000000ull;
    bh_init(&s,mode==14?"0123456789abcdef0123456789abcdef":"native-burrowlark",mode==14?UINT64_MAX:1);
    if(mode==14){s.revision=UINT32_MAX-2;for(unsigned i=0;i<5;i++)s.sequence[i]=UINT64_MAX-1000;}
    assert(!power);bh_supply(&s,true,now);bh_connection(&s,true);
    uint64_t end=now+5000;
    for(;now<end;now++){
        if(mode==3&&now==1500)bh_connection(&s,false);
        if(mode==3&&now==2500)bh_connection(&s,true);
        if(mode==4&&now==1500){bh_supply(&s,false,now);assert(!power);}
        if(mode==4&&now==2500){bh_supply(&s,true,now);bh_connection(&s,true);}
        bh_tick(&s,now);if(mode!=5||now<1000||now>2000)drain(&s);
    }drain(&s);if(mode==6)assert(!s.initialized&&!s.count&&!power);
    if(mode==7||mode==11||mode==12)assert(polls==1);
    if(mode==9||mode==10)assert(!polls);
    bh_supply(&s,false,now);assert(!power);return 0;
}
