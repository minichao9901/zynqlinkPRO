#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#define DAP_SELECTIO_VARIABLE 1
static int selectio_dual_rate(void) {return 1;}
#include "selectio_clock_under_test.h"

int main(void) {
    unsigned divisor, half;
    assert(!selectio_clock_plan(50000000U,&divisor,&half) && divisor==32 && half==1);
    assert(!selectio_clock_plan(73000000U,&divisor,&half) && divisor==44 && half==0);
    assert(!selectio_clock_plan(100000000U,&divisor,&half) && divisor==32 && half==0);
    assert(selectio_clock_plan(49999999U,&divisor,&half));
    assert(selectio_clock_plan(100000001U,&divisor,&half));
    for(uint32_t limit=50000000U;limit<=100000000U;limit+=12719U) {
        assert(!selectio_clock_plan(limit,&divisor,&half));
        const uint32_t pll=33333333U*48U;
        assert(divisor>=32 && divisor<=63 && half<=1);
        uint32_t hz=(pll/divisor)*(half ? 1U : 2U);
        assert(hz<=limit);
        for(unsigned d=32;d<=63;d++) {
            const uint32_t rate=pll/d;
            assert(rate>limit || rate<=hz);
            assert(2U*rate>limit || 2U*rate<=hz);
        }
    }
    puts("PASS variable SelectIO profile bounds and divider selection");
}
