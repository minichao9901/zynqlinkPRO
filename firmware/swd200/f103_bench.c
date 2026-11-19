#include <stdint.h>

#define WORDS 256u
#define BASE 0x20008000u
#define M ((volatile uint32_t *)0x2ff40u)
#define P ((volatile const uint32_t *)0x24000u)
#define G ((volatile uint32_t *)0xf8f00200u)
#define A ((volatile uint32_t *)0x40000000u)
#define TX ((volatile uint32_t *)0x40001000u)
#define RX ((volatile uint32_t *)0x40002000u)
enum {MAGIC, REQ, RESP, MIXED, ROUNDS, ERROR, READ_OK, WRITE_OK, SUMMARY,
      BAD_INDEX, BAD_VALUE, READ_WAIT, WRITE_WAIT, READ_TIME, WRITE_TIME=15, TOTAL_TIME=17,
      READ_WALL=19, WRITE_WALL=21, COMPARE=23, GUARD=25};

static uint64_t ticks(void) {
    uint32_t hi, lo;
    do { hi=G[1]; lo=G[0]; } while (hi!=G[1]);
    return ((uint64_t)hi<<32)|lo;
}
static void save(unsigned i, uint64_t t) { M[i]=(uint32_t)t; M[i+1]=(uint32_t)(t>>32); }
static void cmd(unsigned i, unsigned op, uint32_t data) { TX[2*i]=op; TX[2*i+1]=data; }
static unsigned submit(unsigned n, uint64_t *elapsed) {
    if ((A[1]&33)!=33) return 1;
    __asm__ volatile("dsb sy" ::: "memory");
    uint64_t t=ticks();
    A[4]=n;
    for (unsigned k=0;k<200000;k++) {
        if ((A[1]&37)==37) {
            uint32_t s=A[5];
            *elapsed+=ticks()-t;
            M[SUMMARY]=s;
            return (s&65535)==n ? 0 : 2;
        }
    }
    return 3;
}
static unsigned memword(uint32_t addr,uint32_t *value) {
    uint64_t ignored=0;
    cmd(0,5,addr);cmd(1,15,0);cmd(2,14,0);
    unsigned err=submit(3,&ignored);
    if (!err) *value=RX[2];
    return err;
}
#ifndef SWD200_RESIDENT
static unsigned block(unsigned write,uint32_t inversion,uint64_t *time,uint64_t *compare,uint64_t *guard) {
    uint64_t ignored=0;
    unsigned err, first=0;
    if (write) {
        uint64_t t=ticks();
        // Confirm TAR by posted AP read before allowing any DRW write.
        cmd(0,5,BASE);cmd(1,7,0);cmd(2,14,0);
        err=submit(3,&ignored);
        if (err || RX[2]!=BASE) return 4;
        *guard+=ticks()-t;
    } else { cmd(0,5,BASE); first=1; }
    for (unsigned i=0;i<WORDS;i++) cmd(first+i,write?13:15,write?(P[i]^inversion):0);
    cmd(first+WORDS,14,0);cmd(first+WORDS+1,6,0);
    err=submit(first+WORDS+2,time);
    if (err) return err;
    M[write?WRITE_WAIT:READ_WAIT]+=M[SUMMARY]>>16;
    if ((RX[first+WORDS+1]&0xa00000b2u)!=0xa0000000u) return 5;
    uint64_t t=ticks();
    if (!write) for (unsigned i=0;i<WORDS;i++) {
        uint32_t got=RX[first+1+i];
        if (got!=(P[i]^inversion)) { M[BAD_INDEX]=i; M[BAD_VALUE]=got; return 6; }
    }
    if (!write) *compare+=ticks()-t;
    return 0;
}
#endif
#ifdef SWD200_RESIDENT
static void prepare_banks(void) {
    uint32_t guard=A[7]&0x70u;
    A[7]=guard;
    cmd(0,5,BASE);cmd(1,7,0);cmd(2,14,0);
    A[7]=guard|2u;
    for (unsigned i=0;i<WORDS;i++) cmd(i,13,P[i]);
    cmd(WORDS,14,0);cmd(WORDS+1,6,0);
    A[7]=guard|9u;
    cmd(0,5,BASE);
    for (unsigned i=0;i<WORDS;i++) {
        cmd(i+1,15,0);
        ((volatile uint32_t *)0x40003000u)[i]=P[i];
    }
    cmd(WORDS+1,14,0);cmd(WORDS+2,6,0);
    A[7]=guard;
}
static unsigned resident_block(unsigned write,uint32_t inversion,uint64_t *time,uint64_t *guard_time) {
    unsigned guard=A[7]&0x70u, inv=inversion?4u:0u;
    if (write) {
        A[7]=guard;
        unsigned err=submit(3,guard_time);
        if (err || RX[2]!=BASE) return 4;
    }
    A[7]=guard|inv|(write?2u:9u);
    unsigned n=WORDS+(write?2u:3u);
    unsigned err=submit(n,time);
    if (err) return err;
    M[write?WRITE_WAIT:READ_WAIT]+=M[SUMMARY]>>16;
    return (RX[n-1]&0xa00000b2u)==0xa0000000u ? 0 : 5;
}
#endif
void bench_init(void) {
    for (unsigned i=0;i<=GUARD+1;i++) M[i]=0;
    G[2]=1;
    M[MAGIC]=0x4631424du;
}
void bench_poll(void) {
    uint32_t request=M[REQ];
    if (request==M[RESP]) return;
    uint32_t rounds=M[ROUNDS], mixed=M[MIXED], id=0, cpu=0;
    uint64_t read_time=0,write_time=0,read_wall=0,write_wall=0,compare=0,guard=0;
    for (unsigned i=ERROR;i<=GUARD+1;i++) M[i]=0;
    unsigned err=0;
    if (rounds==0 || rounds>65536 || mixed>1 || A[0]!=0x53323030) err=7;
    if (!err && (memword(0xe0042000,&id) || memword(0xe000ed00,&cpu) ||
                 id!=0x10036414 || cpu!=0x411fc231)) err=8;
#ifdef SWD200_RESIDENT
    if (A[8]!=0x424e4b31u) err=9;
    if (!err) prepare_banks();
#endif
    uint64_t start=ticks();
    for (unsigned n=0;n<rounds && !err;n++) {
        uint32_t inversion=mixed && !(n&1u) ? 0xffffffffu : 0;
        if (mixed) {
            uint64_t t=ticks();
#ifdef SWD200_RESIDENT
            err=resident_block(1,inversion,&write_time,&guard);
#else
            err=block(1,inversion,&write_time,&compare,&guard);
#endif
            write_wall+=ticks()-t;
            if (err) break;
            M[WRITE_OK]++;
        }
        uint64_t t=ticks();
#ifdef SWD200_RESIDENT
        err=resident_block(0,inversion,&read_time,&guard);
#else
        err=block(0,inversion,&read_time,&compare,&guard);
#endif
        read_wall+=ticks()-t;
        if (!err) M[READ_OK]++;
    }
    save(TOTAL_TIME,ticks()-start);save(READ_TIME,read_time);save(WRITE_TIME,write_time);
#ifdef SWD200_RESIDENT
    if (!err) {
        uint32_t inv=mixed && (rounds&1u) ? 0xffffffffu : 0;
        for(unsigned i=0;i<WORDS;i++)
            if(RX[i+2]!=(P[i]^inv)) {err=6;M[BAD_INDEX]=i;M[BAD_VALUE]=RX[i+2];break;}
    }
    A[7]&=0x70u;
#endif
    save(READ_WALL,read_wall);save(WRITE_WALL,write_wall);save(COMPARE,compare);save(GUARD,guard);
    M[ERROR]=err;
    __asm__ volatile("dsb sy" ::: "memory");
    M[RESP]=request;
}
