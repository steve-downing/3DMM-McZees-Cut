/* Kauai KCDC/KCD2 decompressor: port of kauai/src/codkauai.cpp (C path).
   usage: kcd < packed-chunk > data ; input starts with 'KCDC'/'KCD2' + BE size */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
static uint8_t *S; static long nS;
static uint32_t rd32(const uint8_t *p){return p[0]|p[1]<<8|p[2]<<16|(uint32_t)p[3]<<24;}
int main(void){
  S=malloc(64<<20); nS=fread(S,1,64<<20,stdin);
  if(nS<9){fprintf(stderr,"short\n");return 1;}
  int k2 = !memcmp(S,"KCD2",4); if(!k2 && memcmp(S,"KCDC",4)){fprintf(stderr,"not packed\n");return 1;}
  long cbDst=(S[4]<<24)|(S[5]<<16)|(S[6]<<8)|S[7];
  uint8_t *src=S+8; long cbSrc=nS-8;
  uint8_t *dst=calloc(cbDst+16,1), *pbDst=dst, *pbT;
  /* pad so 4-byte reads past the end are safe */
  uint8_t *buf=calloc(cbSrc+16,1); memcpy(buf,src,cbSrc);
  uint8_t *pbSrc=buf+1; uint32_t lu; long ibit,cb,dib,cbit;
#define T(i) (lu & (1UL<<(i)))
#define ADV(n) (pbSrc+=(n), lu=rd32(pbSrc-4))
  ADV(4);
  if(!k2){
    for(ibit=0;;){
      if(!T(ibit)){ *pbDst++=(uint8_t)(lu>>(ibit+1)); ibit+=9; }
      else{
        cb=1;
        if(!T(ibit+1)){dib=((lu>>(ibit+2))&63)+0x01; ibit+=8;}
        else if(!T(ibit+2)){dib=((lu>>(ibit+3))&511)+0x41; ibit+=12;}
        else if(!T(ibit+3)){dib=((lu>>(ibit+4))&4095)+0x241; ibit+=16;}
        else{dib=(lu>>(ibit+4))&0xFFFFF; if(dib==0xFFFFF)break; dib+=0x1241; ibit+=24; cb++;}
        ADV(ibit>>3); ibit&=7;
        for(cbit=0;;){ if(!T(ibit+cbit))break; if(++cbit>11){fprintf(stderr,"bad\n");return 1;} }
        cb+=(1L<<cbit)+((lu>>(ibit+cbit+1))&((1L<<cbit)-1));
        ibit+=cbit+cbit+1;
        if(pbDst-dst<dib||pbDst+cb>dst+cbDst){fprintf(stderr,"bad ref\n");return 1;}
        for(pbT=pbDst-dib;cb-->0;)*pbDst++=*pbT++;
      }
      ADV(ibit>>3); ibit&=7;
    }
  } else {
    /* KCD2, read as a bit stream (LSB first), following _FEncode2 */
    long pos=8, nbits=cbSrc*8;
#define BIT(p) ((buf[(p)>>3]>>((p)&7))&1)
    for(;;){
      long i; uint32_t v;
      for(cbit=0;;){ if(pos+cbit>=nbits) goto done; if(!BIT(pos+cbit))break; if(++cbit>11)goto done; }
      pos+=cbit+1;
      for(v=0,i=0;i<cbit;i++) v|=(uint32_t)BIT(pos+i)<<i;
      pos+=cbit; cb=(1L<<cbit)+v;
      if(!BIT(pos)){
        long r, n; uint32_t low=0, high=0;
        pos++;
        r=pos&7; /* bits already used in the current byte */
        if(pbDst+cb>dst+cbDst){fprintf(stderr,"bad lit\n");return 1;}
        if(r){ n=8-r; for(i=0;i<n;i++) low|=(uint32_t)BIT(pos+i)<<i; pos+=n; } else { n=0; r=8; }
        for(i=0;i<cb-1;i++){ *pbDst++=buf[pos>>3]; pos+=8; }
        for(i=0;i<r;i++) high|=(uint32_t)BIT(pos+i)<<i;
        pos+=r;
        *pbDst++=(uint8_t)(low | (high<<n));
      } else {
        uint32_t off;
        cb++;
        if(!BIT(pos+1)){ for(off=0,i=0;i<6;i++) off|=(uint32_t)BIT(pos+2+i)<<i; dib=off+0x01; pos+=8; }
        else if(!BIT(pos+2)){ for(off=0,i=0;i<9;i++) off|=(uint32_t)BIT(pos+3+i)<<i; dib=off+0x41; pos+=12; }
        else if(!BIT(pos+3)){ for(off=0,i=0;i<12;i++) off|=(uint32_t)BIT(pos+4+i)<<i; dib=off+0x241; pos+=16; }
        else { for(off=0,i=0;i<20;i++) off|=(uint32_t)BIT(pos+4+i)<<i; dib=off+0x1241; pos+=24; cb++; }
        if(pbDst-dst<dib||pbDst+cb>dst+cbDst){fprintf(stderr,"bad ref2 %ld %ld\n",(long)(pbDst-dst),dib);return 1;}
        for(pbT=pbDst-dib;cb-->0;)*pbDst++=*pbT++;
      }
    }
  }
done:
  if(pbDst-dst!=cbDst) fprintf(stderr,"size mismatch %ld vs %ld\n",(long)(pbDst-dst),cbDst);
  fwrite(dst,1,pbDst-dst,stdout); return 0;
}
