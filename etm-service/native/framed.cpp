// FRM1: already synchronized TPIU formatter frames from the Zynq DDR owner.
// Unpacking follows vendored OpenCSD 1.8.3 TraceFmtDcdImpl::unpackFrame().
// Partial final frames lack their flag byte and must never be decoded.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs = std::filesystem;

struct Stream {
    std::ofstream file;
    std::vector<char> buffer;
    uint64_t bytes = 0;
};

static int run(const std::vector<fs::path>& args) {
    if (args.size() == 2 && args[1] == "--version") {
        std::cout << "{\"protocol\":\"etm-framed-native/1\",\"format\":\"FRM1\"}\n";
        return 0;
    }
    if (args.size() != 5 || args[3] != "--tail-bytes")
        throw std::runtime_error("usage: etm_framed INPUT NEW_OUTPUT_DIR --tail-bytes N (0..15)");
    const std::string tail_arg = args[4].string();
    size_t used = 0;
    const unsigned tail = std::stoul(tail_arg, &used);
    if (used != tail_arg.size() || tail > 15) throw std::runtime_error("invalid tail length");
    const uint64_t size = fs::file_size(args[1]);
    if (size % 16 != tail) throw std::runtime_error("FRM1 size disagrees with capture tail length");
    std::ifstream input(args[1], std::ios::binary);
    if (!input) throw std::runtime_error("cannot open input");
    if (!fs::create_directory(args[2])) throw std::runtime_error("output directory must be new");
    std::array<Stream, 127> streams;
    int current = -1;
    uint64_t unknown = 0, padding = 0, changes = 0, frames = 0;
    auto emit = [&](int id, unsigned char value) {
        if (id < 0) { ++unknown; return; }
        if (id == 0) { ++padding; return; }
        auto& stream = streams.at(id);
        if (!stream.file.is_open()) {
            stream.file.open(args[2] / ("id" + std::to_string(id) + ".bin"), std::ios::binary);
            if (!stream.file) throw std::runtime_error("cannot open stream output");
            stream.buffer.reserve(65536);
        }
        stream.buffer.push_back(static_cast<char>(value));
        ++stream.bytes;
        if (stream.buffer.size() == 65536) {
            stream.file.write(stream.buffer.data(), stream.buffer.size());
            if (!stream.file) throw std::runtime_error("stream write failed");
            stream.buffer.clear();
        }
    };
    auto set_id = [&](unsigned char value) {
        const int next = value >> 1;
        if (next == 127) throw std::runtime_error("reserved source ID 127 in FRM1");
        if (next != current) ++changes;
        current = next;
    };
    const auto start = std::chrono::steady_clock::now();
    // Fixed-size input/output buffers; memory use does not scale with capture size.
    std::array<unsigned char, 65536> block;
    uint64_t remaining = size - tail;
    while (remaining) {
        const size_t count = static_cast<size_t>(std::min<uint64_t>(remaining, block.size()));
        input.read(reinterpret_cast<char*>(block.data()), count);
        if (static_cast<size_t>(input.gcount()) != count) throw std::runtime_error("short frame read");
        for (size_t offset = 0; offset < count; offset += 16) {
            const auto* frame = block.data() + offset;
            const unsigned flags = frame[15];
            for (int pos = 0; pos < 14; pos += 2) {
                const unsigned flag = (flags >> (pos / 2)) & 1;
                if (frame[pos] & 1) {
                    const int old = current, next = frame[pos] >> 1;
                    set_id(frame[pos]);
                    emit(flag && next != old ? old : current, frame[pos + 1]);
                } else {
                    emit(current, frame[pos] | flag);
                    emit(current, frame[pos + 1]);
                }
            }
            if (frame[14] & 1) set_id(frame[14]);
            else emit(current, frame[14] | ((flags >> 7) & 1));
            ++frames;
        }
        remaining -= count;
    }
    std::array<char, 15> tail_buffer;
    input.read(tail_buffer.data(), tail);
    if (static_cast<unsigned>(input.gcount()) != tail || input.peek() != EOF)
        throw std::runtime_error("input changed while reading");
    std::string sources = "{";
    bool first = true;
    for (size_t id = 1; id < streams.size(); ++id) {
        auto& stream = streams[id];
        if (!stream.file.is_open()) continue;
        stream.file.write(stream.buffer.data(), stream.buffer.size());
        stream.file.close();
        if (stream.file.fail()) throw std::runtime_error("stream close failed");
        if (!first) sources += ",";
        first = false;
        sources += "\"" + std::to_string(id) + "\":" + std::to_string(stream.bytes);
    }
    sources += "}";
    const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    std::ofstream report(args[2] / "result.json", std::ios::binary);
    report << "{\"protocol\":\"etm-framed-native/1\",\"format\":\"FRM1\",\"inputBytes\":" << size
           << ",\"frames\":" << frames << ",\"trailingFrameBytes\":" << tail
           << ",\"unknownBytes\":" << unknown << ",\"paddingBytes\":" << padding
           << ",\"idChanges\":" << changes << ",\"streams\":" << sources
           << ",\"seconds\":" << elapsed << "}\n";
    report.close();
    if (report.fail()) throw std::runtime_error("report write failed");
    return 0;
}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
        std::vector<fs::path> args;
        for (int i = 0; i < argc; ++i) args.emplace_back(argv[i]);
        return run(args);
    } catch (const std::exception& e) {
        std::cerr << "FRM1 deformat failed: " << e.what() << "\n";
        return 1;
    }
}
