#pragma once
#include <cstdint>
#include <string>
namespace etm_decode {
struct ElemView {
    int etype;
    uint8_t id;
    int isa;
    uint32_t flags;
    uint32_t cycle;
    bool has_cc;
    uint64_t timestamp;
    bool has_ts;
    unsigned last_exec;
    unsigned last_cond;
    int last_type;
    int last_subtype;
    uint32_t payload;
    uint64_t offset;
    uint64_t start;
    uint64_t end;
    bool exception;
    bool excep_ret;
    bool range;
    bool needs_text;
};
struct Sink {
    virtual ~Sink() = default;
    virtual void element(const ElemView&, const char*) = 0;
    virtual void packet(uint64_t, uint32_t, uint32_t, const uint8_t*) = 0;
    virtual void status(uint32_t, int, const char*, const char*) = 0;
};
int decode(const std::string& trace, const std::string& config, Sink& sink);
}
