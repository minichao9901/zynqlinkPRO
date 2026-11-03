// Read-only, generation-bound native TraceStore session. Python receives DTOs,
// never container blocks, query arrays or execution reconstruction state.
#pragma once
#include "unicode_lower.hpp"
struct NativeCursor {
    const uint8_t *data;
    size_t size, pos = 0;
    NativeCursor(const std::vector<uint8_t> &bytes) : data(bytes.data()), size(bytes.size()) {}
    NativeCursor(const uint8_t *bytes, size_t n) : data(bytes), size(n) {}
    void need(size_t n) const {
        if (pos > size || n > size - pos)
            fail(kExitInput, "Truncated native store field");
    }
    uint64_t le(size_t n) {
        need(n);
        uint64_t v = 0;
        for (size_t i = 0; i < n; ++i)
            v |= uint64_t(data[pos++]) << (8 * i);
        return v;
    }
    uint64_t uv() {
        uint64_t v = 0;
        for (unsigned shift = 0; shift <= 63; shift += 7) {
            auto b = le(1);
            if (shift == 63 && b > 1)
                fail(kExitInput, "Store varint overflows");
            v |= (b & 127) << shift;
            if (!(b & 128))
                return v;
        }
        fail(kExitInput, "Invalid store varint");
    }
    int64_t sv() {
        const auto v = uv();
        return int64_t(v >> 1) ^ -int64_t(v & 1);
    }
    std::string pair() {
        auto n = uv();
        need(n);
        std::string s(reinterpret_cast<const char *>(data + pos), n);
        pos += n;
        return s;
    }
};
struct NativeArray {
    uint8_t dtype = 0, ndim = 1;
    uint64_t rows = 0, cols = 0, offset = 0, length = 0, raw_size = 0;
    uint32_t crc = 0;
    bool decoded = false;
    std::vector<uint8_t> raw;
    static size_t width(uint8_t type) {
        static const size_t widths[] = {1, 1, 2, 2, 4, 4, 8, 8, 4, 8};
        if (type > 9)
            fail(kExitInput, "Unknown query dtype");
        return widths[type];
    }
    size_t count() const { return rows * (ndim == 2 ? cols : 1); }
    int64_t at(size_t index) const {
        if (index >= count())
            fail(kExitInput, "Query array index out of range");
        size_t n = width(dtype);
        if (index * n > raw.size() || n > raw.size() - index * n)
            fail(kExitInput, "Query table was not decoded");
        const uint8_t *p = raw.data() + index * n;
        switch (dtype) {
        case 0:
            return *p;
        case 1: {
            int8_t v;
            std::memcpy(&v, p, 1);
            return v;
        }
        case 2: {
            uint16_t v;
            std::memcpy(&v, p, 2);
            return v;
        }
        case 3: {
            int16_t v;
            std::memcpy(&v, p, 2);
            return v;
        }
        case 4: {
            uint32_t v;
            std::memcpy(&v, p, 4);
            return v;
        }
        case 5: {
            int32_t v;
            std::memcpy(&v, p, 4);
            return v;
        }
        case 6: {
            uint64_t v;
            std::memcpy(&v, p, 8);
            if (v > uint64_t(INT64_MAX))
                fail(kExitInput, "Query integer exceeds signed range");
            return v;
        }
        case 7: {
            int64_t v;
            std::memcpy(&v, p, 8);
            return v;
        }
        default:
            fail(kExitInput, "Expected integral query table");
        }
    }
    size_t lower(int64_t value) const {
        size_t lo = 0, hi = count();
        while (lo < hi) {
            size_t mid = lo + (hi - lo) / 2;
            if (at(mid) < value)
                lo = mid + 1;
            else
                hi = mid;
        }
        return lo;
    }
    size_t upper(int64_t value) const {
        size_t lo = 0, hi = count();
        while (lo < hi) {
            size_t mid = lo + (hi - lo) / 2;
            if (at(mid) <= value)
                lo = mid + 1;
            else
                hi = mid;
        }
        return lo;
    }
};
struct NativeRow {
    uint64_t seq = 0, offset = 0, cycles = 0, span = 0;
    uint32_t id = 0;
    uint8_t state = 0, type = 0;
    Json event;
};

void native_index_npz(CompleteIndexResult &index) {
    index.meta["container"] = "v1";
    const auto &payload = index.payload;
    NativeCursor header(payload);
    header.pos = 12;
    size_t count = header.le(4), names = 20 + count * 64;
    std::ostringstream zip(std::ios::binary), directory(std::ios::binary);
    size_t entries = 0;
    auto u16 = [](std::ostream &out, uint16_t value) {
        out.put(char(value));
        out.put(char(value >> 8));
    };
    static const char *dtypes[] = {"|u1", "|i1", "<u2", "<i2", "<u4",
                                   "<i4", "<u8", "<i8", "<f4", "<f8"};
    for (size_t i = 0; i < count; ++i) {
        NativeCursor row(payload.data() + 20 + i * 64, 64);
        auto name_offset = row.le(4), name_length = row.le(2), type = row.le(1), ndim = row.le(1);
        row.le(4);
        auto rows = row.le(8), cols = row.le(8), offset = row.le(8), compressed = row.le(8),
             raw_size = row.le(8), crc = row.le(4);
        std::string name(reinterpret_cast<const char *>(payload.data() + names + name_offset),
                         name_length);
        std::vector<uint8_t> raw(raw_size);
        uint8_t empty = 0;
        z_stream z{};
        z.next_in = const_cast<Bytef *>(payload.data() + offset);
        z.avail_in = compressed;
        z.next_out = raw_size ? raw.data() : &empty;
        z.avail_out = raw_size ? raw_size : 1;
        inflateInit(&z);
        auto status = inflate(&z, Z_FINISH);
        bool valid = status == Z_STREAM_END && z.total_in == compressed && z.total_out == raw_size;
        inflateEnd(&z);
        if (!valid || crc32_bytes(raw.data(), raw.size()) != crc)
            fail(kExitConsistency, "Native reencode source CRC differs");
        if (name == "meta_json") {
            auto text = python_json(index.meta);
            raw.assign(text.begin(), text.end());
            rows = raw.size();
        }
        std::string shape = "(" + std::to_string(rows) + ",";
        if (ndim == 2)
            shape += " " + std::to_string(cols) + ",";
        shape += ")";
        std::string h = "{'descr': '" + std::string(dtypes[type]) +
                        "', 'fortran_order': False, 'shape': " + shape + ", }";
        h.append((64 - (10 + h.size() + 1) % 64) % 64, ' ');
        h += '\n';
        std::ostringstream npy(std::ios::binary);
        npy.write("\x93NUMPY", 6);
        npy.put(1);
        npy.put(0);
        u16(npy, h.size());
        npy.write(h.data(), h.size());
        npy.write(reinterpret_cast<const char *>(raw.data()), raw.size());
        auto bytes_ = npy.str();
        std::vector<uint8_t> input(bytes_.begin(), bytes_.end()), deflate = zlib_compress(input, 1);
        if (deflate.size() < 6)
            fail(kExitConsistency, "Invalid native DEFLATE stream");
        const auto file = name + ".npy";
        const uint32_t start = zip.tellp(), checksum = crc32_bytes(input.data(), input.size()),
                       length = deflate.size() - 6;
        write_u32(zip, 0x04034b50);
        u16(zip, 20);
        u16(zip, 0);
        u16(zip, 8);
        u16(zip, 0);
        u16(zip, 0);
        write_u32(zip, checksum);
        write_u32(zip, length);
        write_u32(zip, input.size());
        u16(zip, file.size());
        u16(zip, 0);
        zip.write(file.data(), file.size());
        zip.write(reinterpret_cast<const char *>(deflate.data() + 2), length);
        write_u32(directory, 0x02014b50);
        u16(directory, 20);
        u16(directory, 20);
        u16(directory, 0);
        u16(directory, 8);
        u16(directory, 0);
        u16(directory, 0);
        write_u32(directory, checksum);
        write_u32(directory, length);
        write_u32(directory, input.size());
        u16(directory, file.size());
        u16(directory, 0);
        u16(directory, 0);
        u16(directory, 0);
        u16(directory, 0);
        write_u32(directory, 0);
        write_u32(directory, start);
        directory.write(file.data(), file.size());
        ++entries;
    }
    auto central = directory.str();
    uint32_t start = zip.tellp();
    zip.write(central.data(), central.size());
    write_u32(zip, 0x06054b50);
    u16(zip, 0);
    u16(zip, 0);
    u16(zip, entries);
    u16(zip, entries);
    write_u32(zip, central.size());
    write_u32(zip, start);
    u16(zip, 0);
    auto data = zip.str();
    index.payload.assign({'E', 'T', 'M', 'Q', 'I', 'D', 'X', '1', 1});
    index.payload.insert(index.payload.end(), data.begin(), data.end());
}

class NativeStore {
  public:
    struct Block {
        uint64_t offset;
        uint32_t length, count;
        uint16_t type, flags;
        uint32_t crc;
    };
    fs::path folder, path;
    std::ifstream input;
    Json manifest, meta, summary, sources, query_meta;
    uint64_t first = 0, last = 0, total = 0, instructions = 0, tag = 0, file_bytes = 0;
    uint32_t required = 0, optional = 0;
    std::vector<Block> blocks;
    std::vector<size_t> sequence_blocks, packet_blocks;
    std::vector<std::string> strings;
    std::vector<Json> static_rows;
    std::vector<uint8_t> predicated;
    std::vector<Json> aggregates;
    std::vector<std::array<uint64_t, 3>> checkpoints;
    std::map<std::string, NativeArray> arrays;
    std::vector<uint8_t> query_payload;
    std::map<size_t, std::shared_ptr<std::vector<uint8_t>>> block_cache;
    std::deque<size_t> cache_order;
    std::vector<std::vector<int32_t>> chains, children;
    std::vector<std::vector<std::string>> paths;
    bool paths_ready = false;
    Json issue_values;
    bool issues_checked = false;
    bool transient_index = false;
    static Json read_json(const fs::path &path, size_t cap) {
        std::error_code ec;
        auto size = fs::file_size(path, ec);
        if (ec || size > cap)
            fail(kExitInput, "Invalid native JSON file");
        std::ifstream in(file_path(path.u8string()), std::ios::binary);
        if (!in)
            fail(kExitIo, "Cannot read native JSON");
        return Json::parse(in);
    }
    static std::string hash_file(const fs::path &path) {
        std::ifstream in(file_path(path.u8string()), std::ios::binary);
        if (!in)
            fail(kExitIo, "Cannot hash native store");
        FastSha256 sha;
        std::vector<char> data(1 << 20);
        while (in) {
            in.read(data.data(), data.size());
            if (in.gcount())
                sha.update(data.data(), in.gcount());
        }
        if (!in.eof())
            fail(kExitIo, "Native store hash read failed");
        return sha.hex_digest();
    }
    NativeStore(const fs::path &directory, const Json &declared, bool verify = true,
                const fs::path &file_override = {})
        : folder(directory), manifest(declared) {
        if (manifest.value("state", std::string()) != "complete" ||
            manifest.value("schemaVersion", 0) != 1)
            fail(kExitVersion, "Store is not complete/schema1");
        auto generation = manifest.at("generation").get<std::string>();
        if (generation.empty() || generation == ".." ||
            generation.find_first_of("/\\") != std::string::npos)
            fail(kExitInput, "Unsafe store generation");
        tag = std::stoull(manifest.at("generationTag").get<std::string>(), nullptr, 0);
        bool found = false;
        for (const auto &f : manifest.at("files")) {
            const auto name = f.at("name").get<std::string>();
            if (name.empty() || name == ".." || name.find_first_of("/\\") != std::string::npos)
                fail(kExitInput, "Unsafe store file name");
            auto file = name == "store.bin" && !file_override.empty()
                            ? file_override
                            : folder / "generations" / generation / fs::u8path(name);
            if (fs::file_size(file_path(file.u8string())) != f.at("bytes").get<uint64_t>())
                fail(kExitConsistency, "Store file size differs from manifest");
            if (verify && hash_file(file) != f.at("sha256").get<std::string>())
                fail(kExitConsistency, "Store SHA256 differs from manifest");
            if (name == "store.bin") {
                path = file;
                file_bytes = f.at("bytes");
                found = true;
            }
        }
        if (!found)
            fail(kExitInput, "Manifest has no execution store");
        input.open(file_path(path.u8string()), std::ios::binary);
        if (!input)
            fail(kExitIo, "Cannot open native store");
        auto header = read(0, 56);
        NativeCursor h(header);
        if (std::memcmp(header.data(), "ETMTSv1\0", 8) != 0)
            fail(kExitVersion, "Unknown store magic");
        h.pos = 8;
        if (h.le(2) != 1 || h.le(2) != 1 || h.le(4) != 0x01020304)
            fail(kExitVersion, "Unknown store format/order");
        if (h.le(8) != tag)
            fail(kExitConsistency, "Store generation tag differs");
        auto count = h.le(4);
        required = h.le(4);
        if (required & ~2u || !count || count > (1u << 20) || count > (file_bytes - 56) / 24)
            fail(kExitInput, "Store flags/directory invalid");
        auto payload_size = h.le(8);
        if (h.le(8) != file_bytes || h.le(4) != crc32_bytes(header.data(), 48))
            fail(kExitConsistency, "Store header length/CRC invalid");
        optional = h.le(4);
        auto directory_bytes = read(56, count * 24);
        NativeCursor d(directory_bytes);
        uint64_t next = 56 + count * 24;
        for (size_t i = 0; i < count; ++i) {
            Block b{d.le(8),           uint32_t(d.le(4)), uint32_t(d.le(4)),
                    uint16_t(d.le(2)), uint16_t(d.le(2)), uint32_t(d.le(4))};
            if (b.offset != next || b.offset > file_bytes || b.length > file_bytes - b.offset ||
                b.length > (128u << 20) || b.type < 1 || b.type > 12 || b.flags & ~1u)
                fail(kExitInput, "Invalid native store block");
            next += b.length;
            blocks.push_back(b);
            if (b.type == 3)
                sequence_blocks.push_back(i);
            if (b.type == 4)
                packet_blocks.push_back(i);
        }
        if (next != file_bytes || payload_size != file_bytes - 56 - count * 24)
            fail(kExitConsistency, "Store payload extent differs");
        meta = json_block(7, true);
        summary = json_block(8, true);
        sources = json_block(9, false);
        if (sources.is_null())
            sources = Json::object();
        first = meta.at("seq").at("first");
        last = meta.at("seq").at("last");
        total = meta.at("counts").at("events");
        instructions = meta.at("counts").at("instructions");
        if (last < first || last - first + 1 != total)
            fail(kExitInput, "Non-contiguous native store is not supported");
        load_static();
        load_aggregate();
        load_index();
    }
    std::vector<uint8_t> read(uint64_t offset, size_t size) {
        if (offset > file_bytes || size > file_bytes - offset)
            fail(kExitInput, "Read exceeds native store");
        std::vector<uint8_t> data(size);
        input.clear();
        input.seekg(offset);
        if (size)
            input.read(reinterpret_cast<char *>(data.data()), size);
        if (!input)
            fail(kExitIo, "Truncated native store");
        return data;
    }
    std::vector<size_t> of_type(unsigned type) const {
        std::vector<size_t> ids;
        for (size_t n = 0; n < blocks.size(); ++n)
            if (blocks[n].type == type)
                ids.push_back(n);
        return ids;
    }
    std::shared_ptr<std::vector<uint8_t>> block(size_t n) {
        auto cached = block_cache.find(n);
        if (cached != block_cache.end())
            return cached->second;
        const auto &b = blocks.at(n);
        auto data = read(b.offset, b.length);
        if (crc32_bytes(data.data(), data.size()) != b.crc)
            fail(kExitConsistency, "Store block CRC mismatch");
        if (b.flags & 1) {
            const uint64_t cap = b.type == 10 ? 128u << 20 : 64u << 20;
            if (b.count > cap)
                fail(kExitInput, "Inflated store block exceeds reader limit");
            std::vector<uint8_t> decoded(b.count);
            uLongf length = b.count;
            z_stream stream{};
            stream.next_in = data.data();
            stream.avail_in = data.size();
            stream.next_out = decoded.data();
            stream.avail_out = decoded.size();
            if (inflateInit(&stream) != Z_OK)
                fail(kExitInput, "Cannot inflate block");
            int status = inflate(&stream, Z_FINISH);
            bool valid = status == Z_STREAM_END && stream.total_out == decoded.size() &&
                         stream.total_in == data.size();
            inflateEnd(&stream);
            if (!valid)
                fail(kExitConsistency, "Inflated block length/trailer mismatch");
            data = std::move(decoded);
        }
        auto value = std::make_shared<std::vector<uint8_t>>(std::move(data));
        block_cache[n] = value;
        cache_order.push_back(n);
        while (cache_order.size() > 16) {
            block_cache.erase(cache_order.front());
            cache_order.pop_front();
        }
        return value;
    }
    Json json_block(unsigned type, bool required_) {
        auto ids = of_type(type);
        if (ids.empty()) {
            if (required_)
                fail(kExitInput, "Missing store JSON block");
            return nullptr;
        }
        if (ids.size() != 1)
            fail(kExitInput, "Duplicate store JSON block");
        auto data = block(ids[0]);
        return Json::parse(data->begin(), data->end());
    }
    void load_static() {
        for (auto n : of_type(1)) {
            auto data = block(n);
            NativeCursor c(*data);
            while (c.pos < c.size) {
                auto value = c.pair();
                if (native_utf8_replace(value) != value)
                    fail(kExitInput, "Store string is not UTF-8");
                strings.push_back(std::move(value));
                if (strings.size() > (1u << 24))
                    fail(kExitInput, "Too many store strings");
            }
        }
        auto text = [&](uint64_t id) -> const std::string & {
            if (id >= strings.size())
                fail(kExitInput, "Static string id out of range");
            return strings[id];
        };
        for (auto n : of_type(2)) {
            auto data = block(n);
            NativeCursor c(*data);
            while (c.pos < c.size) {
                const uint64_t pc = c.uv();
                auto size = c.le(1), flags = c.le(1), flow = c.le(1);
                if (size < 1 || size > 16 || flags & ~31u || flow > 4)
                    fail(kExitInput, "Invalid native static instruction");
                c.need(size);
                std::string code;
                const char *hex = "0123456789abcdef";
                for (size_t j = 0; j < size; ++j) {
                    auto b = c.le(1);
                    code += hex[b >> 4];
                    code += hex[b & 15];
                }
                auto mnemonic = text(c.uv()), operands = text(c.uv());
                Json fn = nullptr, file = nullptr, line = nullptr;
                if (flags & 4)
                    fn = text(c.uv());
                if (flags & 8)
                    file = text(c.uv());
                if (flags & 16)
                    line = c.uv();
                static const char *flows[] = {"linear", "call", "return", "branch", "unknown"};
                static_rows.push_back(Json{{"pc", pc},
                                           {"size", size},
                                           {"bytes", code},
                                           {"mnemonic", mnemonic},
                                           {"operands", operands},
                                           {"function", fn},
                                           {"file", file},
                                           {"line", line},
                                           {"flow", flows[flow]},
                                           {"conditional", bool(flags & 2)},
                                           {"predicated", bool(flags & 1)}});
                predicated.push_back(bool(flags & 1));
            }
            if (c.pos != c.size)
                fail(kExitInput, "Extra static bytes");
        }
        if (static_rows.empty() ||
            static_rows.size() != meta.at("counts").at("staticPcs").get<size_t>())
            fail(kExitConsistency, "Native static count differs");
    }
    void load_aggregate() {
        static const char *names[] = {"blockIndex",   "firstSeq",   "lastSeq", "recordCount",
                                      "instructions", "executed",   "unknown", "notTaken",
                                      "cycles",       "rareEvents", "calls",   "returns",
                                      "exceptions",   "boundaries"};
        auto ids = of_type(6);
        if (ids.size() != 1)
            fail(kExitInput, "Missing aggregate block");
        auto data = block(ids[0]);
        NativeCursor c(*data);
        while (c.pos < c.size) {
            Json a = Json::object();
            for (auto key : names)
                a[key] = c.uv();
            aggregates.push_back(std::move(a));
        }
        if (aggregates.size() != sequence_blocks.size())
            fail(kExitConsistency, "Aggregate block count differs");
        for (auto n : of_type(11)) {
            auto bytes_ = block(n);
            NativeCursor p(*bytes_);
            uint64_t seq = 0;
            while (p.pos < p.size) {
                seq += p.uv();
                auto b = p.uv(), o = p.uv();
                if (b >= sequence_blocks.size())
                    fail(kExitInput, "Invalid checkpoint block");
                checkpoints.push_back({seq, b, o});
            }
        }
        if (checkpoints.empty() || checkpoints.front()[0] != first)
            fail(kExitInput, "Missing initial checkpoint");
    }
    CompleteIndexResult regenerate_index() {
        StaticDict dictionary;
        dictionary.has_extension = true;
        dictionary.version = 1;
        dictionary.strings = {""};
        for (size_t id = 0; id < static_rows.size(); ++id) {
            const auto &row = static_rows[id];
            StaticEntry e;
            e.id = id;
            e.pc = row.at("pc");
            e.size = row.at("size");
            e.predicated = row.at("predicated");
            e.conditional = row.at("conditional");
            e.code_bytes = e.size;
            e.flags = 1;
            e.text_slots = 4;
            e.text_base = dictionary.strings.size();
            std::string code = row.at("bytes");
            for (size_t b = 0; b < e.size; ++b)
                e.code[b] = std::stoul(code.substr(b * 2, 2), nullptr, 16);
            const auto flow = row.at("flow").get<std::string>();
            e.flow = flow == "linear"   ? 0
                     : flow == "call"   ? 1
                     : flow == "return" ? 2
                     : flow == "branch" ? 3
                                        : 4;
            if (!row.at("function").is_null())
                e.flags |= 2;
            if (!row.at("file").is_null())
                e.flags |= 4;
            if (!row.at("line").is_null()) {
                e.flags |= 8;
                e.line = row.at("line");
            }
            for (auto key : {"function", "file", "mnemonic", "operands"})
                dictionary.strings.push_back(
                    row.at(key).is_null() ? std::string() : row.at(key).get<std::string>());
            dictionary.by_pc[e.pc] = id;
            dictionary.entries.push_back(e);
        }
        std::vector<const StaticEntry *> entries;
        for (const auto &e : dictionary.entries)
            entries.push_back(&e);
        ExecutionFacts facts;
        facts.initialize(dictionary, entries);
        facts.enable_index_facts(dictionary, entries, instructions);
        facts.fact_ids.reserve(instructions);
        facts.fact_states.reserve(instructions);
        BuildOutput output;
        output.instructions = instructions;
        output.events = total;
        uint64_t expected = first;
        for (size_t b = 0; b < sequence_blocks.size(); ++b) {
            auto bytes_ = block(sequence_blocks[b]);
            NativeCursor c(*bytes_);
            while (c.pos < c.size) {
                size_t record = c.pos;
                auto type = c.le(1), length = c.uv();
                c.need(length);
                NativeCursor r(c.data + c.pos, length);
                c.pos += length;
                if (type == 3)
                    continue;
                auto seq = r.uv();
                if (seq != expected)
                    fail(kExitConsistency, "Legacy execution sequence has a gap");
                if (type == 1) {
                    auto count = r.uv(), tail = r.le(1), offset = r.uv(), cycles = r.uv(),
                         span = r.uv(), unknown = r.uv(), id = r.uv();
                    if (!count || count > 4096 || tail > 2)
                        fail(kExitInput, "Legacy RUN fields invalid");
                    uint64_t internal = 0;
                    for (size_t i = 0; i < count; ++i) {
                        if (i) {
                            auto delta = r.sv();
                            if (delta < 0) {
                                uint64_t mag = uint64_t(-(delta + 1)) + 1;
                                if (mag > id)
                                    fail(kExitInput, "Legacy id underflow");
                                id -= mag;
                            } else
                                id += uint64_t(delta);
                        }
                        if (id >= entries.size())
                            fail(kExitInput, "Legacy static id invalid");
                        uint8_t state = predicated[id] ? 2 : i + 1 == count ? tail : 0;
                        if (i + 1 < count)
                            internal += predicated[id];
                        facts.instruction(*entries[id], state, seq - first + i, b, record, i);
                        if (i + 1 == count && cycles)
                            facts.fact_cycles.push_back({facts.fact_ids.size() - 1, seq - first + i,
                                                         cycles, uint32_t(span)});
                    }
                    if (internal != unknown)
                        fail(kExitConsistency, "Legacy predicate count invalid");
                    expected += count;
                    if (!facts.fact_runs.empty() && facts.fact_runs.front().ordinal == 0)
                        output.first_instruction = facts.fact_runs.front().seq;
                } else if (type == 2) {
                    auto t = r.le(1), offset = r.uv(), payload = r.uv(), begin = r.uv(),
                         end = r.uv(), flags = r.uv(), text = r.uv();
                    if (!is_event_type(t) || text >= strings.size())
                        fail(kExitInput, "Legacy event invalid");
                    facts.event(seq - first, t, flags, payload, end, strings[text]);
                    ++expected;
                } else
                    fail(kExitInput, "Legacy record type invalid");
                if (r.pos != r.size)
                    fail(kExitInput, "Legacy record contains trailing fields");
            }
        }
        if (expected != last + 1 || facts.fact_ids.size() != instructions)
            fail(kExitConsistency, "Legacy execution counts differ");
        return CompleteIndex(dictionary, entries, facts, output).build();
    }
    void load_index(bool rebuilding = false) {
        auto ids = of_type(12);
        if (ids.size() > 1)
            fail(kExitInput, "Duplicate query index");
        if (!rebuilding) {
            if (ids.empty()) {
                query_payload = regenerate_index().payload;
                transient_index = true;
            } else
                query_payload = *block(ids[0]);
        }
        if (query_payload.size() >= 9 && std::memcmp(query_payload.data(), "ETMQIDX1", 8) == 0 &&
            query_payload[8] == 1) {
            load_npz();
            const auto &bytes_ = array("meta_json").raw;
            query_meta = Json::parse(bytes_.begin(), bytes_.end());
            if (!query_meta.contains("container"))
                query_meta["container"] = "v1";
            complete_loaded_index();
            return;
        }
        if (query_payload.size() < 20 || std::memcmp(query_payload.data(), "ETMQIDX2", 8) != 0)
            fail(kExitVersion,
                 "Native reader requires a v2 index; rebuild/reencode this legacy index");
        NativeCursor c(query_payload);
        c.pos = 8;
        if (c.le(4) != 2)
            fail(kExitVersion, "Unknown native query ABI");
        auto count = c.le(4);
        if (c.le(4) || !count || count > 256 || count > (query_payload.size() - 20) / 64)
            fail(kExitInput, "Invalid query table directory");
        const size_t name_start = 20 + count * 64;
        for (size_t i = 0; i < count; ++i) {
            c.pos = 20 + i * 64;
            auto name_offset = c.le(4), name_size = c.le(2);
            NativeArray a;
            a.dtype = c.le(1);
            a.ndim = c.le(1);
            if (c.le(4))
                fail(kExitInput, "Reserved query bytes are nonzero");
            a.rows = c.le(8);
            a.cols = c.le(8);
            a.offset = c.le(8);
            a.length = c.le(8);
            a.raw_size = c.le(8);
            a.crc = c.le(4);
            if (c.le(4) || c.le(4) || a.ndim < 1 || a.ndim > 2 || a.offset > query_payload.size() ||
                a.length > query_payload.size() - a.offset || a.raw_size > (2ull << 30) ||
                name_start + name_offset > query_payload.size() ||
                name_size > query_payload.size() - name_start - name_offset)
                fail(kExitInput, "Invalid query table extent");
            auto width = NativeArray::width(a.dtype);
            if (a.rows > uint64_t(-1) / width ||
                a.ndim == 2 && (a.cols && a.rows * width > uint64_t(-1) / a.cols) ||
                a.rows * width * (a.ndim == 2 ? a.cols : 1) != a.raw_size)
                fail(kExitInput, "Invalid query array shape");
            auto name = std::string(
                reinterpret_cast<const char *>(query_payload.data() + name_start + name_offset),
                name_size);
            if (!arrays.emplace(name, std::move(a)).second)
                fail(kExitInput, "Duplicate query table name");
        }
        const auto &bytes_ = array("meta_json").raw;
        query_meta = Json::parse(bytes_.begin(), bytes_.end());
        complete_loaded_index();
    }
    void complete_loaded_index() {
        bool complete = true;
        for (const auto *key : {"node_parent", "ps_start", "fs_start", "pc_cells",
                                "cycle_anchor_seq", "unknown_seq", "cell_anchor_block"})
            complete &= arrays.count(key) != 0;
        if (!complete) {
            if (transient_index)
                fail(kExitInput, "Cannot reconstruct complete legacy index");
            query_payload = regenerate_index().payload;
            arrays.clear();
            transient_index = true;
            load_index(true);
            return;
        }
        if (transient_index && first) {
            for (const auto *key : {"cell_first_seq", "ev_seq", "unknown_seq", "not_taken_seq",
                                    "call_pair_seq", "cycle_anchor_seq"}) {
                auto &values = array(key);
                for (size_t i = 0; i < values.count(); ++i) {
                    uint64_t value = values.at(i) + first;
                    if (values.dtype == 5) {
                        if (value > INT32_MAX)
                            fail(kExitInput, "Legacy sequence exceeds int32 query ABI");
                        int32_t n = value;
                        std::memcpy(values.raw.data() + i * 4, &n, 4);
                    } else if (values.dtype == 7) {
                        int64_t n = value;
                        std::memcpy(values.raw.data() + i * 8, &n, 8);
                    } else
                        fail(kExitInput, "Unexpected sequence array type");
                }
            }
            query_meta["firstSeq"] = first;
            query_meta["lastSeq"] = last;
            query_meta["coverage"] = Json::array({first, last});
        }
        validate_index();
    }
    void load_npz() {
        const size_t base = 9, size = query_payload.size() - base;
        const auto *zip = query_payload.data() + base;
        auto le = [&](size_t p, size_t n) {
            if (p > size || n > size - p)
                fail(kExitInput, "Truncated legacy query archive");
            NativeCursor c(zip + p, n);
            return c.le(n);
        };
        size_t eocd = size;
        for (size_t p = size >= 22 ? size - 22 : 0;; --p) {
            if (le(p, 4) == 0x06054b50) {
                eocd = p;
                break;
            }
            if (!p || size - p > 65557)
                break;
        }
        if (eocd == size || le(eocd + 4, 2) || le(eocd + 6, 2) ||
            le(eocd + 8, 2) != le(eocd + 10, 2))
            fail(kExitInput, "Invalid legacy query ZIP directory");
        size_t count = le(eocd + 10, 2), cursor = le(eocd + 16, 4);
        if (!count || count > 256 || cursor > eocd)
            fail(kExitInput, "Legacy query table count invalid");
        for (size_t i = 0; i < count; ++i) {
            if (le(cursor, 4) != 0x02014b50)
                fail(kExitInput, "Invalid ZIP member");
            auto flags = le(cursor + 8, 2), method = le(cursor + 10, 2), crc = le(cursor + 16, 4),
                 compressed = le(cursor + 20, 4), decoded = le(cursor + 24, 4),
                 names = le(cursor + 28, 2), extra = le(cursor + 30, 2),
                 comment = le(cursor + 32, 2), local = le(cursor + 42, 4);
            if (flags & 1 || decoded > (2ull << 30) || cursor + 46 > size ||
                names > size - cursor - 46)
                fail(kExitInput, "Legacy ZIP member extent invalid");
            std::string name(reinterpret_cast<const char *>(zip + cursor + 46), names);
            cursor += 46 + names + extra + comment;
            if (name.size() < 5 || name.substr(name.size() - 4) != ".npy")
                fail(kExitInput, "Unexpected legacy query member");
            name.resize(name.size() - 4);
            if (le(local, 4) != 0x04034b50)
                fail(kExitInput, "Invalid ZIP local member");
            size_t data = local + 30 + le(local + 26, 2) + le(local + 28, 2);
            if (data > size || compressed > size - data)
                fail(kExitInput, "ZIP member exceeds archive");
            std::vector<uint8_t> npy(decoded);
            if (method == 0) {
                if (compressed != decoded)
                    fail(kExitInput, "Stored ZIP length differs");
                std::memcpy(npy.data(), zip + data, decoded);
            } else if (method == 8) {
                z_stream z{};
                z.next_in = const_cast<Bytef *>(zip + data);
                z.avail_in = compressed;
                z.next_out = npy.data();
                z.avail_out = npy.size();
                if (inflateInit2(&z, -MAX_WBITS) != Z_OK)
                    fail(kExitInput, "Cannot read legacy query DEFLATE");
                auto result = inflate(&z, Z_FINISH);
                bool valid =
                    result == Z_STREAM_END && z.total_in == compressed && z.total_out == decoded;
                inflateEnd(&z);
                if (!valid)
                    fail(kExitConsistency, "Legacy query DEFLATE length differs");
            } else
                fail(kExitInput, "Unsupported legacy query compression");
            if (crc32_bytes(npy.data(), npy.size()) != crc)
                fail(kExitConsistency, "Legacy query ZIP CRC differs");
            if (npy.size() < 10 || std::memcmp(npy.data(), "\x93NUMPY", 6) != 0)
                fail(kExitInput, "Invalid legacy NumPy array");
            size_t version = npy[6], header_offset = version == 1 ? 10 : 12;
            NativeCursor h(npy.data() + 8, npy.size() - 8);
            size_t header_length = h.le(version == 1 ? 2 : 4);
            if (version < 1 || version > 3 || header_offset > npy.size() ||
                header_length > npy.size() - header_offset)
                fail(kExitInput, "Invalid NumPy header");
            std::string header(reinterpret_cast<const char *>(npy.data() + header_offset),
                               header_length);
            std::smatch match;
            if (!std::regex_search(header, match,
                                   std::regex("['\"]descr['\"]\\s*:\\s*['\"]([^'\"]+)['\"]")))
                fail(kExitInput, "NumPy dtype missing");
            std::string dtype = match[1];
            if (dtype.empty() || dtype[0] == '>')
                fail(kExitInput, "Unsupported NumPy byte order");
            if (dtype[0] == '<' || dtype[0] == '|' || dtype[0] == '=')
                dtype.erase(0, 1);
            const std::map<std::string, uint8_t> types{{"u1", 0}, {"b1", 0}, {"i1", 1}, {"u2", 2},
                                                       {"i2", 3}, {"u4", 4}, {"i4", 5}, {"u8", 6},
                                                       {"i8", 7}, {"f4", 8}, {"f8", 9}};
            auto type = types.find(dtype);
            if (type == types.end())
                fail(kExitInput, "Unsupported/pickled NumPy dtype");
            if (!std::regex_search(header, match,
                                   std::regex("['\"]shape['\"]\\s*:\\s*\\(([^)]*)\\)")))
                fail(kExitInput, "NumPy shape missing");
            std::string shape = match[1];
            std::vector<uint64_t> dimensions;
            std::regex numeric("[0-9]+");
            for (auto p = std::sregex_iterator(shape.begin(), shape.end(), numeric);
                 p != std::sregex_iterator(); ++p)
                dimensions.push_back(std::stoull(p->str()));
            if (dimensions.empty() || dimensions.size() > 2)
                fail(kExitInput, "Unsupported NumPy dimensions");
            NativeArray a;
            a.dtype = type->second;
            a.ndim = dimensions.size();
            a.rows = dimensions[0];
            a.cols = a.ndim == 2 ? dimensions[1] : 0;
            size_t width = NativeArray::width(a.dtype);
            if (a.rows > (2ull << 30) / width ||
                a.ndim == 2 && a.cols && a.rows * width > (2ull << 30) / a.cols)
                fail(kExitInput, "Legacy query matrix too large");
            a.raw_size = a.rows * width * (a.ndim == 2 ? a.cols : 1);
            size_t body = header_offset + header_length;
            if (a.raw_size != npy.size() - body)
                fail(kExitConsistency, "NumPy body length differs");
            a.raw.assign(npy.begin() + body, npy.end());
            if (a.ndim == 2 &&
                std::regex_search(header, std::regex("['\"]fortran_order['\"]\\s*:\\s*True"))) {
                auto copy = a.raw;
                for (size_t r = 0; r < a.rows; ++r)
                    for (size_t c = 0; c < a.cols; ++c)
                        std::memcpy(a.raw.data() + (r * a.cols + c) * width,
                                    copy.data() + (c * a.rows + r) * width, width);
            }
            a.decoded = true;
            a.crc = crc32_bytes(a.raw.data(), a.raw.size());
            if (!arrays.emplace(name, std::move(a)).second)
                fail(kExitInput, "Duplicate legacy query table");
        }
    }
    void validate_index() {
        if (query_meta.at("instructions") != instructions ||
            query_meta.at("staticCount") != static_rows.size() ||
            query_meta.at("firstSeq") != first || query_meta.at("lastSeq") != last)
            fail(kExitConsistency, "Query metadata differs from execution");
        auto &ev = array("ev_seq");
        if (ev.count() + instructions != total)
            fail(kExitConsistency, "Event/instruction totals differ");
        for (size_t i = 0; i < ev.count(); ++i)
            if (ev.at(i) < int64_t(first) || ev.at(i) > int64_t(last) ||
                i && ev.at(i) <= ev.at(i - 1))
                fail(kExitInput, "Event index is not ordered");
        auto &pc = array("st_pc");
        auto &sizes = array("st_size");
        auto &pred = array("st_pred");
        if (pc.count() != static_rows.size() || sizes.count() != pc.count() ||
            pred.count() != pc.count())
            fail(kExitConsistency, "Static query mapping length differs");
        for (size_t i = 0; i < pc.count(); ++i)
            if (pc.at(i) != static_rows[i].at("pc").get<int64_t>() ||
                sizes.at(i) != static_rows[i].at("size").get<int64_t>() ||
                pred.at(i) != predicated[i])
                fail(kExitConsistency, "Static query mapping differs");
        const uint64_t cells = (instructions + 4095) / 4096;
        auto &seq = array("cell_first_seq");
        auto &blocks_ = array("cell_anchor_block");
        auto &offsets = array("cell_anchor_offset");
        auto &skips = array("cell_anchor_skip");
        if (seq.count() != cells || blocks_.count() != cells || offsets.count() != cells ||
            skips.count() != cells)
            fail(kExitConsistency, "Cell anchor count differs");
        for (size_t i = 0; i < cells; ++i)
            if (seq.at(i) != int64_t(seq_of(i * 4096)) || blocks_.at(i) < 0 ||
                uint64_t(blocks_.at(i)) >= sequence_blocks.size() || offsets.at(i) < 0 ||
                skips.at(i) < 0 || skips.at(i) >= 4096)
                fail(kExitConsistency, "Invalid native cell anchor");
    }
    NativeArray &array(const std::string &name) {
        auto it = arrays.find(name);
        if (it == arrays.end())
            fail(kExitInput, "Required query table is missing: " + name);
        auto &a = it->second;
        if (!a.decoded) {
            a.raw.resize(a.raw_size);
            uint8_t empty = 0;
            z_stream stream{};
            stream.next_in = query_payload.data() + a.offset;
            stream.avail_in = a.length;
            stream.next_out = a.raw_size ? a.raw.data() : &empty;
            stream.avail_out = a.raw_size ? a.raw.size() : 1;
            if (inflateInit(&stream) != Z_OK)
                fail(kExitInput, "Cannot inflate query table");
            int result = inflate(&stream, Z_FINISH);
            bool valid = result == Z_STREAM_END && stream.total_in == a.length &&
                         stream.total_out == a.raw_size;
            inflateEnd(&stream);
            if (!valid || crc32_bytes(a.raw.data(), a.raw.size()) != a.crc)
                fail(kExitConsistency, "Query table length/CRC mismatch");
            a.decoded = true;
        }
        return a;
    }
    int64_t value(const std::string &name, size_t i) { return array(name).at(i); }
    uint64_t ordinal_before(uint64_t seq) {
        auto &events = array("ev_seq");
        return std::min<uint64_t>(instructions, seq < first ? 0 : seq - first - events.lower(seq));
    }
    uint64_t seq_of(uint64_t ordinal) {
        auto &events = array("ev_seq");
        size_t lo = 0, hi = events.count();
        while (lo < hi) {
            auto mid = (lo + hi) / 2;
            if (uint64_t(events.at(mid)) - first - mid <= ordinal)
                lo = mid + 1;
            else
                hi = mid;
        }
        return first + ordinal + lo;
    }
    bool is_event(uint64_t seq) {
        auto &ev = array("ev_seq");
        auto p = ev.lower(seq);
        return p < ev.count() && uint64_t(ev.at(p)) == seq;
    }
    uint64_t next_instruction(uint64_t seq) {
        auto &ev = array("ev_seq");
        size_t p = ev.lower(seq);
        while (p < ev.count() && uint64_t(ev.at(p)) == seq) {
            ++p;
            ++seq;
        }
        return seq;
    }
    int64_t previous_instruction(int64_t seq) {
        auto &ev = array("ev_seq");
        size_t p = ev.upper(seq);
        while (p && ev.at(p - 1) == seq) {
            --p;
            --seq;
        }
        return seq;
    }
    void prepare_paths() {
        if (paths_ready)
            return;
        auto &parents = array("node_parent");
        auto &labels = array("node_label");
        size_t n = parents.count();
        if (!n || labels.count() != n)
            fail(kExitInput, "Path table length mismatch");
        chains.resize(n);
        paths.resize(n);
        children.resize(n);
        for (size_t i = 0; i < n; ++i) {
            auto p = parents.at(i);
            if (i == 0 ? p != -1 : p < 0 || uint64_t(p) >= i)
                fail(kExitInput, "Path parent is not a tree");
            if (i) {
                chains[i] = chains[p];
                paths[i] = paths[p];
                paths[i].push_back(query_meta.at("strings").at(labels.at(i)).get<std::string>());
                children[p].push_back(i);
            }
            chains[i].push_back(i);
            if (chains[i].size() > 10000)
                fail(kExitInput, "Path depth exceeds reader limit");
        }
        paths_ready = true;
    }
    size_t leaf(uint64_t ordinal) {
        auto &starts = array("ps_start");
        size_t p = starts.upper(ordinal);
        if (!p)
            fail(kExitInput, "Path does not cover instruction");
        --p;
        if (ordinal >= uint64_t(starts.at(p) + value("ps_count", p)))
            fail(kExitInput, "Path gap in query index");
        return value("ps_leaf", p);
    }
    Json instruction(const NativeRow &row) {
        prepare_paths();
        const auto &s = static_rows.at(row.id);
        Json full{{"kind", "instruction"},
                  {"seq", row.seq},
                  {"offset", row.offset},
                  {"pc", s.at("pc")},
                  {"size", s.at("size")},
                  {"bytes", s.at("bytes")},
                  {"mnemonic", s.at("mnemonic")},
                  {"operands", s.at("operands")},
                  {"executed", row.state == 2 ? Json(nullptr) : Json(row.state == 0)},
                  {"function", s.at("function")},
                  {"file", s.at("file")},
                  {"line", s.at("line")},
                  {"cycleCount", row.cycles},
                  {"cycleSpan", row.span},
                  {"flow", s.at("flow")},
                  {"conditional", s.at("conditional")},
                  {"executionState", row.state == 0   ? "executed"
                                     : row.state == 1 ? "not-taken"
                                                      : "unknown"},
                  {"executionReason",
                   row.state == 2 ? "IT 非分支条件指令：当前 trace 未记录条件结果" : ""},
                  {"callPath", paths.at(leaf(ordinal_before(row.seq)))},
                  {"cycles", row.cycles}};
        Json result = Json::object();
        for (const auto &key : meta.at("fieldPresence").at("instruction"))
            result[key.get<std::string>()] = full.at(key.get<std::string>());
        return result;
    }
    template <class Consumer> void rows(uint64_t lo, uint64_t hi, Consumer &&consume) {
        if (lo > hi || lo > last || hi < first)
            return;
        lo = std::max(lo, first);
        hi = std::min(hi, last);
        const uint64_t ordinal = ordinal_before(lo);
        uint64_t base = ordinal;
        if (is_event(lo) && base)
            --base;
        size_t cell = std::min<uint64_t>(base / 4096, (instructions - 1) / 4096);
        size_t block_ordinal = value("cell_anchor_block", cell),
               position = value("cell_anchor_offset", cell), skip = value("cell_anchor_skip", cell);
        if (lo < uint64_t(value("cell_first_seq", 0))) {
            block_ordinal = 0;
            position = 0;
            skip = 0;
        }
        bool anchored = position != 0 || lo >= uint64_t(value("cell_first_seq", 0));
        for (size_t b = block_ordinal; b < sequence_blocks.size(); ++b) {
            auto data = block(sequence_blocks[b]);
            NativeCursor c(*data);
            c.pos = b == block_ordinal ? position : 0;
            while (c.pos < c.size) {
                auto type = c.le(1), length = c.uv();
                c.need(length);
                size_t end = c.pos + length;
                NativeCursor r(c.data + c.pos, length);
                c.pos = end;
                if (type == 3)
                    continue;
                auto seq = r.uv();
                if (type == 1) {
                    auto count = r.uv(), tail = r.le(1), offset = r.uv(), cycles = r.uv(),
                         span = r.uv(), unknown = r.uv(), id = r.uv();
                    if (!count || count > 4096 || tail > 2 || skip >= count)
                        fail(kExitInput, "Invalid native RUN");
                    uint64_t internal_unknown = 0;
                    for (size_t i = 0; i < count; ++i) {
                        if (i) {
                            int64_t delta = r.sv();
                            if (delta < 0) {
                                uint64_t magnitude = uint64_t(-(delta + 1)) + 1;
                                if (magnitude > id)
                                    fail(kExitInput, "RUN id underflows");
                                id -= magnitude;
                            } else {
                                if (uint64_t(delta) > UINT64_MAX - id)
                                    fail(kExitInput, "RUN id overflows");
                                id += uint64_t(delta);
                            }
                        }
                        if (id >= static_rows.size())
                            fail(kExitInput, "RUN id exceeds static table");
                        if (i + 1 < count)
                            internal_unknown += predicated[id];
                        if (i < skip)
                            continue;
                        NativeRow row;
                        row.seq = seq + i;
                        row.id = id;
                        row.offset = offset;
                        row.state = predicated[id] ? 2 : i + 1 == count ? tail : 0;
                        row.cycles = i + 1 == count ? cycles : 0;
                        row.span = i + 1 == count ? span : 0;
                        if (row.seq > hi)
                            return;
                        if (row.seq >= lo && !consume(row))
                            return;
                    }
                    if (r.pos != r.size || internal_unknown != unknown)
                        fail(kExitConsistency, "RUN length/predicate count mismatch");
                    skip = 0;
                    anchored = false;
                } else if (type == 2) {
                    if (skip || anchored)
                        fail(kExitInput, "Instruction anchor points to event");
                    NativeRow row;
                    row.seq = seq;
                    row.type = r.le(1);
                    auto offset = r.uv(), payload = r.uv(), start = r.uv(), finish = r.uv(),
                         flags = r.uv(), text_id = r.uv();
                    if (!is_event_type(row.type) || text_id >= strings.size() || r.pos != r.size)
                        fail(kExitInput, "Invalid native event");
                    row.event = Json{{"kind", "event"},
                                     {"seq", seq},
                                     {"type", row.type},
                                     {"offset", offset},
                                     {"text", strings[text_id]},
                                     {"payload", payload},
                                     {"start", start},
                                     {"end", finish},
                                     {"flags", flags}};
                    if (seq > hi)
                        return;
                    if (seq >= lo && !consume(row))
                        return;
                } else
                    fail(kExitInput, "Unknown native sequence record");
            }
        }
    }
    Json event(uint64_t seq) {
        if (seq < first || seq > last)
            fail(kExitInput, "记录序号不存在");
        Json item = nullptr;
        rows(seq, seq, [&](const NativeRow &r) {
            item = r.type ? r.event : instruction(r);
            return false;
        });
        if (item.is_null())
            fail(kExitInput, "记录序号不存在");
        return Json{{"event", item},
                    {"callPath", item.value("callPath", Json::array())},
                    {"stackBasis", "历史 trace 重建，包含未证实祖先；不是当前寄存器快照"}};
    }
    static std::string lower(const std::string &text) { return native_unicode_lower(text); }
    static std::string clean_search(std::string text) {
        for (char &c : text)
            if (c == '\t' || c == '\n')
                c = ' ';
        return lower(text);
    }
    std::vector<bool> match_static(const std::string &needle) {
        std::vector<bool> match;
        for (const auto &s : static_rows) {
            char pc[32];
            std::snprintf(pc, sizeof(pc), "0x%08x", s.at("pc").get<uint32_t>());
            std::string text =
                s.at("function").is_null() ? "" : s.at("function").get<std::string>();
            text += ' ';
            if (!s.at("file").is_null())
                text += s.at("file").get<std::string>();
            text += ' ';
            text += s.at("mnemonic").get<std::string>() + " " +
                    s.at("operands").get<std::string>() + "  " + pc + " " +
                    std::to_string(s.at("pc").get<uint64_t>());
            match.push_back(clean_search(text).find(needle) != std::string::npos);
        }
        return match;
    }
    std::pair<int64_t, int64_t> bounds(const Json &request, bool clamp = false) {
        int64_t lo = request.contains("start") && !request["start"].is_null()
                         ? request["start"].get<int64_t>()
                         : first,
                hi = request.contains("end") && !request["end"].is_null()
                         ? request["end"].get<int64_t>()
                         : last;
        lo = std::max<int64_t>(lo, first);
        hi = std::min<int64_t>(hi, last);
        if (clamp) {
            lo = std::min<int64_t>(lo, last);
            hi = std::max<int64_t>(hi, first);
        }
        if (hi < lo)
            return {lo, lo - 1};
        return {lo, hi};
    }
    Json page(const Json &request) {
        auto view = request.value("view", std::string("events"));
        if (view == "packets")
            return page_packets(request);
        if (view != "events")
            fail(kExitInput, "未知视图");
        size_t limit = std::clamp<int64_t>(request.value("limit", int64_t(150)), 1, 500),
               offset = std::max<int64_t>(0, request.value("offset", int64_t(0)));
        const auto range = bounds(request);
        const auto lo = range.first, hi = range.second;
        const auto needle = lower(request.value("search", std::string()));
        bool hide = request.value("hide_skipped", false);
        if ((hide || !needle.empty()) && hi < lo)
            fail(kExitInput, "区间结束 seq 不能小于起点");
        Json selected = Json::array();
        uint64_t total_ = 0;
        if (needle.empty() && !hide) {
            total_ = hi >= lo ? hi - lo + 1 : 0;
            offset = total_ ? std::min<uint64_t>(offset, ((total_ - 1) / limit) * limit) : 0;
            if (total_)
                rows(lo + offset, hi, [&](const NativeRow &r) {
                    selected.push_back(r.type ? r.event : instruction(r));
                    return selected.size() < limit;
                });
        } else {
            auto matching = match_static(needle);
            auto accept = [&](const NativeRow &r) {
                return r.type ? needle.empty() ||
                                    clean_search("    " + r.event.at("text").get<std::string>())
                                            .find(needle) != std::string::npos
                              : (!hide || r.state != 1) && matching[r.id];
            };
            if (hi >= lo)
                rows(lo, hi, [&](const NativeRow &r) {
                    if (accept(r)) {
                        if (total_ >= offset && selected.size() < limit)
                            selected.push_back(r.type ? r.event : instruction(r));
                        ++total_;
                    }
                    return true;
                });
            auto corrected =
                total_ ? std::min<uint64_t>(offset, ((total_ - 1) / limit) * limit) : 0;
            if (corrected != offset) {
                offset = corrected;
                selected = Json::array();
                uint64_t count = 0;
                if (total_)
                    rows(lo, hi, [&](const NativeRow &r) {
                        if (accept(r) && count++ >= offset) {
                            selected.push_back(r.type ? r.event : instruction(r));
                            if (selected.size() >= limit)
                                return false;
                        }
                        return true;
                    });
            }
        }
        return Json{{"rows", selected}, {"total", total_}, {"offset", offset}, {"limit", limit}};
    }
    template <class Consumer> void packets(Consumer &&consume) {
        uint64_t previous = 0;
        for (auto n : packet_blocks) {
            auto data = block(n);
            NativeCursor c(*data);
            while (c.pos < c.size) {
                uint64_t offset = previous + c.uv(), size = c.uv();
                auto raw = c.pair(), text = c.pair();
                if (raw.size() != size)
                    fail(kExitConsistency, "Packet byte size differs");
                previous = offset;
                if (!consume(offset, raw, text))
                    return;
            }
        }
    }
    Json page_packets(const Json &request) {
        size_t limit = std::clamp<int64_t>(request.value("limit", int64_t(150)), 1, 500),
               offset = std::max<int64_t>(0, request.value("offset", int64_t(0)));
        auto needle = lower(request.value("search", std::string()));
        uint64_t total_ = needle.empty() ? meta.at("counts").at("packets").get<uint64_t>() : 0;
        const char *digits = "0123456789abcdef";
        auto encoded = [&](const std::string &raw) {
            std::string hex;
            hex.reserve(raw.size() * 2);
            for (uint8_t b : raw) {
                hex += digits[b >> 4];
                hex += digits[b & 15];
            }
            return hex;
        };
        if (!needle.empty())
            packets([&](uint64_t p, const std::string &r, const std::string &t) {
                if (lower(t + " " + std::to_string(p) + " " + encoded(r)).find(needle) !=
                    std::string::npos)
                    ++total_;
                return true;
            });
        offset = total_ ? std::min<uint64_t>(offset, ((total_ - 1) / limit) * limit) : 0;
        Json selected = Json::array();
        uint64_t matched = 0;
        packets([&](uint64_t p, const std::string &r, const std::string &t) {
            std::string hex = encoded(r);
            if (!needle.empty() &&
                lower(t + " " + std::to_string(p) + " " + hex).find(needle) == std::string::npos)
                return true;
            if (matched++ >= offset)
                selected.push_back(Json{{"kind", "packet"},
                                        {"offset", p},
                                        {"size", r.size()},
                                        {"hex", hex},
                                        {"text", t}});
            return selected.size() < limit;
        });
        return Json{{"rows", selected}, {"total", total_}, {"offset", offset}, {"limit", limit}};
    }
    Json stats() {
        Json q{{"available", true},
               {"version", query_meta.value("version", 0)},
               {"container", query_meta.value("container", std::string("v2"))},
               {"cellSize", query_meta.value("cellSize", 0)},
               {"cells", query_meta.value("cells", 0)},
               {"segmentCount", query_meta.value("segmentCount", 0)},
               {"functionSegments", query_meta.value("functionSegments", 0)},
               {"defaultViews", Json::array({"timeline", "window"})},
               {"nav", nullptr}};
        if (query_meta.contains("nav")) {
            auto &n = query_meta["nav"];
            q["nav"] = Json{{"cellSize", n.at("cellSize")},
                            {"pcCellPairs", n.at("pcCellPairs")},
                            {"lineRuns", n.at("lineRuns")}};
        }
        Json result = Json::object();
        for (auto key :
             {"events", "instructions", "runs", "ranges", "rareEvents", "staticPcs", "packets"})
            result[key] = meta.at("counts").value(key, Json(nullptr));
        result["blocks"] = aggregates.size();
        result["checkpoints"] = checkpoints.size();
        for (auto pair : std::vector<std::pair<std::string, std::string>>{{"executed", "executed"},
                                                                          {"unknown", "unknown"},
                                                                          {"notTaken", "notTaken"},
                                                                          {"cycles", "cycles"}}) {
            uint64_t n = 0;
            for (const auto &a : aggregates)
                n += a.at(pair.second).get<uint64_t>();
            result[pair.first] = n;
        }
        uint64_t ins = 0, ex = 0, ev = 0;
        for (const auto &a : aggregates) {
            ins += a.at("instructions").get<uint64_t>();
            ex += a.at("executed").get<uint64_t>();
            ev += a.at("rareEvents").get<uint64_t>();
        }
        result["aggregateMatches"] = ins == instructions && ex == meta["counts"]["executed"] &&
                                     ev == meta["counts"]["rareEvents"];
        result["seqRange"] = Json::array({first, last});
        result["queryIndex"] = q;
        return result;
    }
    Json snapshot() {
        Json directory = Json::array();
        for (const auto &b : blocks)
            directory.push_back(Json{{"offset", b.offset},
                                     {"length", b.length},
                                     {"count", b.count},
                                     {"block_type", b.type},
                                     {"flags", b.flags},
                                     {"crc", b.crc}});
        return Json{{"manifest", manifest},    {"meta", meta},
                    {"summary", summary},      {"sources", sources},
                    {"path", path.u8string()}, {"blocks", directory},
                    {"queryMeta", query_meta}, {"stats", stats()}};
    }
    Json issues(const Json &request) {
        const uint64_t offset = std::max<int64_t>(0, request.value("offset", int64_t(0))),
                       limit = std::clamp<int64_t>(request.value("limit", int64_t(100)), 1, 500);
        if (!issues_checked) {
            issue_values = json_block(10, false);
            if (issue_values.is_object()) {
                auto integer = [](const Json &v) {
                    return v.is_number_integer() &&
                           (!v.is_number_integer() || v.get<int64_t>() >= 0);
                };
                if (issue_values.value("format", std::string()) != "etm-issue-runs/1" ||
                    !issue_values.at("reasons").is_array() ||
                    !issue_values.at("extra").is_array() || !integer(issue_values.at("total")))
                    fail(kExitInput, "Invalid diagnostic schema");
                for (const auto &v : issue_values.at("reasons"))
                    if (!v.is_string())
                        fail(kExitInput, "Invalid diagnostic reason");
                for (const auto &v : issue_values.at("extra"))
                    if (!v.is_object())
                        fail(kExitInput, "Invalid extra diagnostic");
                if (issue_values.contains("predicates")) {
                    for (const auto &v : issue_values.at("predicates")) {
                        if (!v.is_array() || v.size() != 3 || !integer(v[0]) || !integer(v[1]) ||
                            !integer(v[2]) || v[1].get<uint64_t>() < v[0].get<uint64_t>())
                            fail(kExitInput, "Invalid predicate diagnostic");
                    }
                    for (const auto &v : issue_values.at("boundaries")) {
                        if (!v.is_array() || v.size() != 3 || !integer(v[0]) || !integer(v[1]) ||
                            !integer(v[2]) ||
                            v[2].get<uint64_t>() >= issue_values.at("reasons").size())
                            fail(kExitInput, "Invalid boundary diagnostic");
                    }
                }
            }
            issues_checked = true;
        }
        auto &values = issue_values;
        if (values.is_null())
            values = Json::array();
        if (values.is_array()) {
            Json result = Json::array();
            for (uint64_t i = offset; i < std::min<uint64_t>(values.size(), offset + limit); ++i)
                result.push_back(values[i]);
            return Json{{"rows", result}, {"total", values.size()}};
        }
        if (values.is_object() && values.contains("rows")) {
            const auto &rows_ = values.at("rows");
            const auto &extra_ = values.at("extra");
            const auto &reasons_ = values.at("reasons");
            if (!rows_.is_array() ||
                values.at("total").get<uint64_t>() != rows_.size() + extra_.size())
                fail(kExitInput, "Invalid legacy compact diagnostic count");
            Json result = Json::array();
            for (size_t i = 0; i < rows_.size(); ++i) {
                const auto &r = rows_[i];
                if (!r.is_array() || r.size() != 6)
                    fail(kExitInput, "Invalid legacy compact diagnostic row");
                for (const auto &v : r)
                    if (!v.is_number_integer() || v.get<int64_t>() < 0)
                        fail(kExitInput, "Invalid legacy diagnostic scalar");
                if (r[1].get<uint64_t>() < r[0].get<uint64_t>() ||
                    r[2].get<uint64_t>() != r[1].get<uint64_t>() - r[0].get<uint64_t>() + 1 ||
                    r[4].get<uint64_t>() >= reasons_.size() || r[5].get<uint64_t>() > 1)
                    fail(kExitInput, "Legacy compact diagnostic range invalid");
                if (i >= offset && result.size() < limit)
                    result.push_back(Json{{"category", r[5] == 0 ? "predicate" : "boundary"},
                                          {"startSeq", r[0]},
                                          {"endSeq", r[1]},
                                          {"records", r[2]},
                                          {"offset", r[3]},
                                          {"reason", reasons_.at(r[4].get<size_t>())}});
            }
            for (size_t i = std::max<int64_t>(0, int64_t(offset) - int64_t(rows_.size()));
                 i < extra_.size() && result.size() < limit; ++i)
                result.push_back(extra_[i]);
            return Json{{"rows", result}, {"total", values.at("total")}};
        }
        if (values.value("format", std::string()) != "etm-issue-runs/1" ||
            !values.contains("predicates"))
            fail(kExitVersion, "Unsupported compact diagnostics");
        const auto &p = values.at("predicates");
        const auto &b = values.at("boundaries");
        const auto &extra = values.at("extra");
        const auto &reasons = values.at("reasons");
        if (values.at("total").get<uint64_t>() != p.size() + b.size() + extra.size())
            fail(kExitConsistency, "Diagnostic count mismatch");
        Json selected = Json::array();
        size_t pi = 0, bi = 0;
        uint64_t n = 0;
        while ((pi < p.size() || bi < b.size()) && n < offset + limit) {
            bool boundary = bi < b.size() && (pi == p.size() ||
                                              b[bi][0].get<uint64_t>() <= p[pi][0].get<uint64_t>());
            const auto &row = boundary ? b[bi++] : p[pi++];
            if (n++ < offset)
                continue;
            if (boundary)
                selected.push_back(Json{{"category", "boundary"},
                                        {"startSeq", row[0]},
                                        {"endSeq", row[0]},
                                        {"records", 1},
                                        {"offset", row[1]},
                                        {"reason", reasons.at(row[2].get<size_t>())}});
            else
                selected.push_back(
                    Json{{"category", "predicate"},
                         {"startSeq", row[0]},
                         {"endSeq", row[1]},
                         {"records", row[1].get<uint64_t>() - row[0].get<uint64_t>() + 1},
                         {"offset", row[2]},
                         {"reason", reasons.at(0)}});
        }
        if (n >= p.size() + b.size())
            for (size_t i = std::max<int64_t>(0, int64_t(offset) - int64_t(p.size() + b.size()));
                 i < extra.size() && selected.size() < limit; ++i)
                selected.push_back(extra[i]);
        return Json{{"rows", selected}, {"total", values["total"]}};
    }
    Json navigate(const Json &request);
    Json window(const Json &request);
    Json timeline(const Json &request);
    Json reindex(const Json &request) {
        const auto generation = request.at("generation").get<std::string>();
        const uint64_t next_tag = request.at("tag").get<uint64_t>();
        if (generation.rfind("g-", 0) != 0 ||
            generation.find_first_of("/\\") != std::string::npos ||
            generation == manifest.at("generation"))
            fail(kExitInput, "Unsafe reindex generation");
        const auto directory = folder / "generations" / fs::u8path(generation);
        std::error_code ec;
        if (!fs::create_directory(file_path(directory.u8string()), ec) || ec)
            fail(kExitIo, "Cannot create new native index generation");
        try {
            auto started = std::chrono::steady_clock::now();
            auto index = regenerate_index();
            auto container = request.value("container", std::string("v2"));
            if (container == "v1")
                native_index_npz(index);
            else if (container != "v2")
                fail(kExitInput, "Unknown native index container");
            if (first)
                fail(kExitInput,
                     "Rebuilding nonzero-origin legacy stores requires an explicit rebase export");
            Json declaration = Json::object();
            for (const auto *key :
                 {"format", "version", "cellSize", "instructions", "events", "cells", "staticCount",
                  "functionCount", "hotspotCount", "nodeCount", "segmentCount", "functionSegments",
                  "firstSeq", "lastSeq", "nav", "container", "tables", "coverage", "defaultViews"})
                declaration[key] = index.meta.at(key);
            declaration["payloadBytes"] = index.payload.size();
            declaration["buildSeconds"] = index.timings.at("totalSeconds");
            declaration["defaultsSeconds"] = index.timings.at("defaultViewsSeconds");
            declaration["builtAtUnix"] = std::time(nullptr);
            declaration["builtBy"] = "native-core-reindex";
            Json next_meta = meta;
            next_meta["queryIndex"] = declaration;
            BuildOutput output;
            output.generation = generation;
            output.generation_tag = next_tag;
            output.required_features = required;
            output.optional_features = optional | 1;
            for (size_t n = 0; n < blocks.size(); ++n) {
                if (blocks[n].type == 12)
                    continue;
                if (blocks[n].type == 7) {
                    add_json_block(output, 7, python_json(next_meta));
                    continue;
                }
                const auto &b = blocks[n];
                BuildBlock copy;
                copy.type = b.type;
                copy.count = b.count;
                copy.flags = b.flags;
                copy.uncompressed = b.flags ? b.count : 0;
                copy.payload = read(b.offset, b.length);
                if (crc32_bytes(copy.payload.data(), copy.payload.size()) != b.crc)
                    fail(kExitConsistency, "Source block CRC changed during reindex");
                output.blocks.push_back(std::move(copy));
            }
            BuildBlock block_;
            block_.type = 12;
            block_.count = index.meta.at("cells");
            block_.payload = std::move(index.payload);
            output.blocks.push_back(std::move(block_));
            const auto temporary = file_path((directory / "store.bin.tmp").u8string()),
                       destination = file_path((directory / "store.bin").u8string());
            write_store(temporary, output);
            fs::rename(temporary, destination);
            Json next_manifest = manifest;
            next_manifest["generation"] = generation;
            std::ostringstream tag_text;
            tag_text << "0x" << std::hex << next_tag;
            next_manifest["generationTag"] = tag_text.str();
            next_manifest["queryIndex"] = declaration;
            Json files = Json::array();
            for (const auto &f : manifest.at("files")) {
                auto name = f.at("name").get<std::string>();
                if (name == "store.bin")
                    files.push_back(Json{
                        {"name", name},
                        {"bytes", output.store_bytes},
                        {"sha256", output.store_sha256},
                        {"blocks", output.blocks.size()},
                        {"payloadBytes", output.store_bytes - 56 - output.blocks.size() * 24}});
                else {
                    fs::copy_file(
                        file_path((folder / "generations" /
                                   manifest.at("generation").get<std::string>() / fs::u8path(name))
                                      .u8string()),
                        file_path((directory / fs::u8path(name)).u8string()));
                    files.push_back(f);
                }
            }
            next_manifest["files"] = files;
            NativeStore verification(folder, next_manifest, true);
            if (verification.meta != next_meta)
                fail(kExitConsistency, "Reindexed native metadata differs");
            return Json{{"ok", true},
                        {"manifest", next_manifest},
                        {"queryIndex", declaration},
                        {"generation", generation},
                        {"seconds", chrono_seconds(started)},
                        {"storeBytes", output.store_bytes}};
        } catch (...) {
            fs::remove_all(file_path(directory.u8string()), ec);
            throw;
        }
    }
    Json call(const Json &request) {
        auto op = request.at("op").get<std::string>();
        if (op == "snapshot")
            return snapshot();
        if (op == "overview")
            return summary;
        if (op == "stats")
            return stats();
        if (op == "reindex")
            return reindex(request);
        if (op == "capture-start") {
            const uint64_t selected = request.at("pc");
            uint64_t first_pc = 0;
            if (meta.contains("captureStartIndex")) {
                const auto &index = meta.at("captureStartIndex");
                if (index.at("version") != 1 ||
                    index.at("firstRecoveredSeq") != summary.at("firstSeq") ||
                    index.at("staticPcsAreRecovered") != true)
                    fail(kExitConsistency, "Invalid capture start index");
                first_pc = index.at("firstRecoveredPC");
            } else
                first_pc = event(summary.at("firstSeq").get<uint64_t>()).at("event").at("pc");
            bool found = false;
            for (const auto &entry : static_rows)
                found |= entry.at("pc") == selected;
            return Json{{"selectedPC", selected},
                        {"firstRecoveredPC", first_pc},
                        {"entryRecovered", found},
                        {"firstMatchesEntry", first_pc == selected}};
        }
        if (op == "static")
            return static_rows;
        if (op == "strings")
            return strings;
        if (op == "sources")
            return sources;
        if (op == "source")
            return Json{
                {"file", request.at("file")},
                {"text", sources.value(request.at("file").get<std::string>(), std::string())}};
        if (op == "event")
            return event(request.at("seq").get<uint64_t>());
        if (op == "page")
            return page(request);
        if (op == "issues")
            return issues(request);
        if (op == "navigate")
            return navigate(request);
        if (op == "window")
            return window(request);
        if (op == "function_timeline")
            return timeline(request);
        if (op == "events") {
            auto b = bounds(request);
            Json result = Json::array();
            if (b.second < b.first)
                return result;
            rows(b.first, b.second, [&](const NativeRow &r) {
                result.push_back(r.type ? r.event : instruction(r));
                return result.size() < 512;
            });
            return result;
        }
        if (op == "position") {
            uint64_t seq = request.at("seq");
            if (seq < first || seq > last)
                fail(kExitInput, "记录序号不存在");
            size_t b = 0;
            while (b + 1 < aggregates.size() &&
                   aggregates[b + 1].at("firstSeq").get<uint64_t>() <= seq)
                ++b;
            auto p = std::upper_bound(
                checkpoints.begin(), checkpoints.end(), seq,
                [](uint64_t s, const std::array<uint64_t, 3> &c) { return s < c[0]; });
            --p;
            return Json{{"seq", seq},
                        {"block", b},
                        {"blockFirst", aggregates[b].at("firstSeq")},
                        {"blockLast", aggregates[b].at("lastSeq")},
                        {"checkpointSeq", (*p)[0]},
                        {"checkpointBlock", (*p)[1]},
                        {"checkpointOffset", (*p)[2]},
                        {"replayInstructions", seq - (*p)[0]},
                        {"validRange", Json::array({first, last})}};
        }
        fail(kExitUsage, "Unknown native query operation");
    }
};

struct NativeAggregate {
    uint64_t total = 0, node_count = 0, hotspot_count = 0;
    std::vector<std::string> functions, strings;
    std::vector<int32_t> node_function, node_label, h_func, h_file, h_line, hotspot_first_id;
    std::vector<uint32_t> st_pc;
    std::vector<std::vector<int32_t>> children;
    std::vector<int64_t> node_first, function_first, function_counts, function_unknown,
        function_not_taken, function_calls, function_interrupts;
    std::vector<int64_t> hotspot_counts, hotspot_unknown, hotspot_cycles, hotspot_first, node_value,
        node_self, node_value_cycles, node_self_cycles;
    Json analysis() {
        std::vector<int64_t> self_cycles(functions.size(), 0), total_cycles(functions.size(), 0);
        for (size_t n = 1; n < node_count; ++n)
            if (node_function[n] >= 0) {
                self_cycles[node_function[n]] += node_self_cycles[n];
                total_cycles[node_function[n]] += node_value_cycles[n];
            }
        const int64_t cycles = std::accumulate(self_cycles.begin(), self_cycles.end(), int64_t(0));
        std::vector<size_t> order(functions.size());
        std::iota(order.begin(), order.end(), 0);
        std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
            return std::make_pair(-function_counts[a], function_first[a]) <
                   std::make_pair(-function_counts[b], function_first[b]);
        });
        Json function_rows = Json::array(), cycle_rows = Json::array();
        int64_t executed = 0, calls = 0;
        for (auto fn : order)
            if (function_counts[fn]) {
                const auto count = function_counts[fn],
                           known = count - function_unknown[fn] - function_not_taken[fn];
                Json percent = cycles ? Json(100.0 * self_cycles[fn] / cycles) : Json(0);
                Json cpi = count && self_cycles[fn] ? Json(double(self_cycles[fn]) / count)
                                                    : Json(nullptr);
                function_rows.push_back(Json{{"function", functions[fn]},
                                             {"instructions", count},
                                             {"knownExecuted", known},
                                             {"unknownExecution", function_unknown[fn]},
                                             {"notTaken", function_not_taken[fn]},
                                             {"calls", function_calls[fn]},
                                             {"interruptEntries", function_interrupts[fn]},
                                             {"selfCycles", self_cycles[fn]},
                                             {"totalCycles", total_cycles[fn]},
                                             {"cyclePercent", percent},
                                             {"cpi", cpi}});
                executed += known;
                calls += function_calls[fn];
            }
        std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
            return std::make_pair(-self_cycles[a], function_first[a]) <
                   std::make_pair(-self_cycles[b], function_first[b]);
        });
        for (auto fn : order)
            if (function_counts[fn] && self_cycles[fn])
                cycle_rows.push_back(Json{{"function", functions[fn]},
                                          {"selfCycles", self_cycles[fn]},
                                          {"cyclePercent", 100.0 * self_cycles[fn] / cycles},
                                          {"instructions", function_counts[fn]},
                                          {"cpi", double(self_cycles[fn]) / function_counts[fn]},
                                          {"calls", function_calls[fn]}});
        order.resize(hotspot_count);
        std::iota(order.begin(), order.end(), 0);
        std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
            return std::make_tuple(-hotspot_cycles[a], -hotspot_counts[a], hotspot_first[a]) <
                   std::make_tuple(-hotspot_cycles[b], -hotspot_counts[b], hotspot_first[b]);
        });
        Json hotspots = Json::array();
        for (auto hs : order)
            if (hotspot_counts[hs])
                hotspots.push_back(
                    Json{{"function", functions[h_func[hs]]},
                         {"file", h_file[hs] < 0 ? Json(nullptr) : Json(strings[h_file[hs]])},
                         {"line", h_line[hs] < 0 ? Json(nullptr) : Json(h_line[hs])},
                         {"records", hotspot_counts[hs]},
                         {"unknown", hotspot_unknown[hs]},
                         {"cycles", hotspot_cycles[hs]},
                         {"pc", hotspot_first_id[hs] < 0 ? 0 : st_pc[hotspot_first_id[hs]]}});
        std::function<Json(int32_t)> flame = [&](int32_t n) {
            auto kids = children[n];
            std::stable_sort(kids.begin(), kids.end(), [&](int32_t a, int32_t b) {
                return std::make_pair(node_first[a], a) < std::make_pair(node_first[b], b);
            });
            Json child = Json::array();
            for (auto k : kids)
                if (node_value[k] > 0)
                    child.push_back(flame(k));
            return Json{{"name", n ? strings[node_label[n]] : "所选执行区间"},
                        {"value", node_value[n]},
                        {"self", node_self[n]},
                        {"selfCycles", node_self_cycles[n]},
                        {"valueCycles", node_value_cycles[n]},
                        {"children", child}};
        };
        Json analysis{
            {"flame", flame(0)},
            {"functions", function_rows},
            {"hotspots", hotspots},
            {"observedCalls", calls},
            {"timing",
             Json{{"totalCycles", cycles},
                  {"cycleRanges", cycle_rows.size()},
                  {"executedInstructions", executed},
                  {"instructions", total},
                  {"cpi", executed && cycles ? Json(double(cycles) / executed) : Json(nullptr)},
                  {"functions", cycle_rows},
                  {"timeFlameAvailable", bool(cycles)},
                  {"basis", cycles ? "所选区间的周期计数（区间末指令记录，可求和）"
                                   : "所选区间没有周期计数数据（目标未启用或 ETMv3 不支持）"}}},
            {"weight", cycles ? "所选区间的路径记录数；周期列才是耗时"
                              : "所选区间的路径记录数（含未成立/未知状态），不是耗时"}};
        return analysis;
    }
};

NativeAggregate native_aggregate(NativeStore &s, uint64_t lo, uint64_t hi, uint64_t begin,
                                 uint64_t end) {
    s.prepare_paths();
    NativeAggregate a;
    a.total = end - begin;
    a.functions = s.query_meta.at("functionNames").get<std::vector<std::string>>();
    a.strings = s.query_meta.at("strings").get<std::vector<std::string>>();
    a.node_count = s.array("node_parent").count();
    a.hotspot_count = s.array("h_func").count();
    a.children = s.children;
    auto ints = [&](const char *key) {
        std::vector<int32_t> out;
        auto &v = s.array(key);
        out.reserve(v.count());
        for (size_t i = 0; i < v.count(); ++i)
            out.push_back(v.at(i));
        return out;
    };
    a.node_label = ints("node_label");
    a.h_func = ints("h_func");
    a.h_file = ints("h_file");
    a.h_line = ints("h_line");
    for (const auto &e : s.static_rows)
        a.st_pc.push_back(e.at("pc"));
    std::map<std::string, int32_t> fn;
    for (size_t i = 0; i < a.functions.size(); ++i)
        fn[a.functions[i]] = i;
    a.node_function.assign(a.node_count, -1);
    for (size_t n = 1; n < a.node_count; ++n) {
        auto f = fn.find(a.strings.at(a.node_label[n]));
        if (f != fn.end())
            a.node_function[n] = f->second;
    }
    const auto fsize = a.functions.size(), hsize = a.hotspot_count, nsize = a.node_count;
    a.function_first.assign(fsize, 1 << 30);
    a.function_counts.assign(fsize, 0);
    a.function_unknown.assign(fsize, 0);
    a.function_not_taken.assign(fsize, 0);
    a.function_calls.assign(fsize, 0);
    a.function_interrupts.assign(fsize, 0);
    a.hotspot_counts.assign(hsize, 0);
    a.hotspot_unknown.assign(hsize, 0);
    a.hotspot_cycles.assign(hsize, 0);
    a.hotspot_first.assign(hsize, 1 << 30);
    a.hotspot_first_id.assign(hsize, -1);
    a.node_first.assign(nsize, 1ll << 62);
    a.node_first[0] = begin;
    a.node_value.assign(nsize, 0);
    a.node_self.assign(nsize, 0);
    a.node_value_cycles.assign(nsize, 0);
    a.node_self_cycles.assign(nsize, 0);
    if (begin >= end)
        return a;
    auto &counts = s.array("cell_hotspot_count");
    auto &unknown = s.array("cell_hotspot_unknown");
    auto &earliest = s.array("cell_hotspot_first");
    auto &node_values = s.array("cell_node_value");
    auto &node_cycles = s.array("cell_node_value_cycles");
    uint64_t covered_low = (begin + 4095) / 4096, covered_end = end / 4096;
    if (end == s.instructions && end % 4096)
        covered_end = (end + 4095) / 4096;
    if (covered_end < covered_low)
        covered_end = covered_low;
    for (uint64_t cell = covered_low; cell < covered_end; ++cell) {
        for (size_t h = 0; h < hsize; ++h) {
            auto count = counts.at(cell * hsize + h);
            a.hotspot_counts[h] += count;
            a.hotspot_unknown[h] += unknown.at(cell * hsize + h);
            if (count && a.hotspot_first_id[h] < 0) {
                auto packed = uint64_t(earliest.at(cell * hsize + h));
                a.hotspot_first[h] = cell * 4096 + (packed & 4095);
                a.hotspot_first_id[h] = packed >> 12;
            }
        }
        for (size_t n = 0; n < nsize; ++n) {
            a.node_value[n] += node_values.at(cell * nsize + n);
            a.node_value_cycles[n] += node_cycles.at(cell * nsize + n);
        }
    }
    auto &hs_cells = s.array("hs_cycles_cells");
    auto &hs_ids = s.array("hs_cycles_hotspots");
    auto &hs_values = s.array("hs_cycles_values");
    for (size_t i = hs_cells.lower(covered_low), e = hs_cells.lower(covered_end); i < e; ++i)
        a.hotspot_cycles.at(hs_ids.at(i)) += hs_values.at(i);
    auto &self_cells = s.array("node_self_cells");
    auto &self_ids = s.array("node_self_nodes");
    auto &self_counts = s.array("node_self_counts");
    auto &self_cycles = s.array("node_self_cycles");
    for (size_t i = self_cells.lower(covered_low), e = self_cells.lower(covered_end); i < e; ++i) {
        auto n = self_ids.at(i);
        a.node_self.at(n) += self_counts.at(i);
        a.node_self_cycles.at(n) += self_cycles.at(i);
    }
    std::vector<std::pair<uint64_t, uint64_t>> partial;
    if (covered_low >= covered_end)
        partial.push_back({begin, end});
    else {
        if (begin < covered_low * 4096)
            partial.push_back({begin, covered_low * 4096});
        if (end > covered_end * 4096)
            partial.push_back({covered_end * 4096, end});
    }
    auto &st_hotspot = s.array("st_hotspot");
    for (auto part : partial)
        if (part.first < part.second)
            s.rows(s.seq_of(part.first), s.seq_of(part.second - 1), [&](const NativeRow &r) {
                if (r.type)
                    return true;
                auto ordinal = s.ordinal_before(r.seq);
                auto hs = st_hotspot.at(r.id);
                auto leaf = s.leaf(ordinal);
                ++a.hotspot_counts.at(hs);
                a.hotspot_unknown.at(hs) += s.predicated[r.id];
                a.hotspot_cycles.at(hs) += r.cycles;
                if (ordinal < uint64_t(a.hotspot_first[hs])) {
                    a.hotspot_first[hs] = ordinal;
                    a.hotspot_first_id[hs] = r.id;
                }
                for (auto n : s.chains.at(leaf)) {
                    ++a.node_value[n];
                    a.node_value_cycles[n] += r.cycles;
                }
                ++a.node_self[leaf];
                a.node_self_cycles[leaf] += r.cycles;
                return true;
            });
    auto &fs_start = s.array("fs_start");
    auto &fs_count = s.array("fs_count");
    auto &fs_func = s.array("fs_func");
    size_t i = fs_start.upper(begin);
    if (i)
        --i;
    for (; i < fs_start.count() && uint64_t(fs_start.at(i)) < end; ++i) {
        uint64_t b = std::max<uint64_t>(begin, fs_start.at(i)),
                 e = std::min<uint64_t>(end, fs_start.at(i) + fs_count.at(i));
        if (e > b) {
            auto f = fs_func.at(i);
            a.function_counts.at(f) += e - b;
            a.function_first.at(f) = std::min<int64_t>(a.function_first.at(f), b);
        }
    }
    uint64_t seq_begin = s.seq_of(begin), seq_end = s.seq_of(end - 1);
    for (const auto &spec : std::vector<std::pair<std::string, std::vector<int64_t> *>>{
             {"unknown", &a.function_unknown}, {"not_taken", &a.function_not_taken}}) {
        auto &seq = s.array(spec.first + "_seq");
        auto &func = s.array(spec.first + "_func");
        for (size_t p = seq.lower(seq_begin), e = seq.upper(seq_end); p < e; ++p)
            ++spec.second->at(func.at(p));
    }
    auto &call_seq = s.array("call_pair_seq");
    auto &call_func = s.array("call_pair_func");
    for (size_t p = call_seq.lower(seq_begin), e = call_seq.lower(seq_end); p < e; ++p)
        ++a.function_calls.at(call_func.at(p));
    auto &ev_seq = s.array("ev_seq");
    auto &ev_type = s.array("ev_type");
    auto &ev_next = s.array("ev_next_func");
    for (size_t p = ev_seq.lower(lo), e = ev_seq.upper(hi); p < e; ++p)
        if (ev_type.at(p) == 9 && uint64_t(ev_seq.at(p)) < hi && ev_next.at(p) >= 0)
            ++a.function_interrupts.at(ev_next.at(p));
    auto &ps_start = s.array("ps_start");
    auto &ps_leaf = s.array("ps_leaf");
    size_t p = ps_start.upper(begin);
    if (p)
        --p;
    for (; p < ps_start.count() && uint64_t(ps_start.at(p)) < end; ++p) {
        auto first_ = std::max<uint64_t>(ps_start.at(p), begin);
        for (auto n : s.chains.at(ps_leaf.at(p)))
            a.node_first[n] = std::min<int64_t>(a.node_first[n], first_);
    }
    return a;
}

Json NativeStore::window(const Json &request) {
    auto range = bounds(request, true);
    if (range.second < range.first)
        fail(kExitInput, "区间结束序号不能小于起点");
    uint64_t lo = range.first, hi = range.second;
    int bins = std::clamp<int64_t>(request.value("bins", int64_t(1200)), 100, 2000);
    if (!(transient_index && first) && lo == first && hi == last && bins == 1200 &&
        arrays.count("default_window_json")) {
        auto &bytes_ = array("default_window_json").raw;
        const auto &declared = query_meta.at("defaultViews").at("window");
        FastSha256 hash;
        hash.update(bytes_.data(), bytes_.size());
        if (hash.hex_digest() != declared.at("sha256"))
            fail(kExitConsistency, "Default window SHA mismatch");
        return Json::parse(bytes_.begin(), bytes_.end());
    }
    prepare_paths();
    uint64_t begin = ordinal_before(lo), end = ordinal_before(hi + 1), span = hi - lo + 1,
             step = (span + bins - 1) / bins;
    Json timeline = Json::array();
    auto &ev_seq = array("ev_seq");
    auto &ev_type = array("ev_type");
    auto &ev_text = array("ev_text");
    auto &unknown = array("unknown_seq");
    auto &not_taken = array("not_taken_seq");
    auto &ps_start = array("ps_start");
    auto &ps_count = array("ps_count");
    auto &ps_leaf = array("ps_leaf");
    for (uint64_t low = lo; low <= hi; low += step) {
        uint64_t high = std::min(hi, low + step - 1), b = ordinal_before(low),
                 e = ordinal_before(high + 1);
        Json events = Json::array();
        for (size_t i = ev_seq.lower(low), stop = ev_seq.upper(high); i < stop; ++i)
            events.push_back(Json{{"seq", ev_seq.at(i)},
                                  {"type", ev_type.at(i)},
                                  {"text", query_meta.at("strings").at(ev_text.at(i))}});
        std::vector<std::string> prefix;
        bool present = false, mixed = false;
        if (e > b) {
            size_t i = ps_start.upper(b);
            if (i)
                --i;
            for (; i < ps_start.count() && uint64_t(ps_start.at(i)) < e; ++i) {
                if (uint64_t(ps_start.at(i) + ps_count.at(i)) <= b)
                    continue;
                const auto &value = paths.at(ps_leaf.at(i));
                if (!present) {
                    prefix = value;
                    present = true;
                } else if (prefix != value) {
                    mixed = true;
                    size_t n = 0;
                    while (n < prefix.size() && n < value.size() && prefix[n] == value[n])
                        ++n;
                    prefix.resize(n);
                }
            }
        }
        if (mixed)
            prefix.push_back("多段调用（放大查看）");
        timeline.push_back(Json{{"startSeq", low},
                                {"endSeq", high},
                                {"firstSeq", low},
                                {"path", prefix},
                                {"records", e - b},
                                {"unknown", unknown.upper(high) - unknown.lower(low)},
                                {"notTaken", not_taken.upper(high) - not_taken.lower(low)},
                                {"mixed", mixed},
                                {"events", events}});
    }
    auto aggregate = native_aggregate(*this, lo, hi, begin, end);
    Json analysis = aggregate.analysis();
    return Json{
        {"range", Json{{"start", lo}, {"end", hi}, {"totalStart", first}, {"totalEnd", last}}},
        {"firstSeq", end > begin ? Json(seq_of(begin)) : Json(nullptr)},
        {"timing", Json{{"axis", "execution-order"},
                        {"verifiedTime", false},
                        {"reason", "当前记录没有已验收的逐指令时间戳，执行序号不能换算为微秒"}}},
        {"timeline", timeline},
        {"resolution", step},
        {"analysis", analysis}};
}

Json NativeStore::timeline(const Json &request) {
    auto range = bounds(request, true);
    if (range.second < range.first)
        fail(kExitInput, "区间结束序号不能小于起点");
    uint64_t lo = range.first, hi = range.second, span = hi - lo + 1;
    size_t bins = std::clamp<int64_t>(request.value("bins", int64_t(1600)), 240, 2400),
           max_functions = std::clamp<int64_t>(request.value("max_functions", int64_t(6)), 1, 10);
    const auto needle = lower(request.value("search", std::string()));
    bool hide = request.value("hide_skipped", false);
    if (!(transient_index && first) && lo == first && hi == last && bins == 1600 &&
        max_functions == 6 && needle.empty() && !hide && arrays.count("default_timeline_json")) {
        auto &bytes_ = array("default_timeline_json").raw;
        FastSha256 hash;
        hash.update(bytes_.data(), bytes_.size());
        if (hash.hex_digest() != query_meta.at("defaultViews").at("timeline").at("sha256"))
            fail(kExitConsistency, "Default timeline SHA mismatch");
        return Json::parse(bytes_.begin(), bytes_.end());
    }
    auto functions = query_meta.at("functionNames").get<std::vector<std::string>>();
    size_t fsize = functions.size();
    std::vector<int64_t> counts(bins * fsize, 0), unknown(bins, 0), not_taken(bins, 0),
        totals(fsize, 0);
    Json markers = Json::array();
    std::map<uint64_t, size_t> marker_bins;
    uint64_t filtered = 0, marker_count = 0;
    auto add_marker = [&](uint64_t seq, int type) {
        ++marker_count;
        size_t bin = std::min<uint64_t>(bins - 1, (seq - lo) * bins / span);
        auto found = marker_bins.emplace(bin, markers.size());
        if (found.second)
            markers.push_back(
                Json{{"startSeq", seq}, {"endSeq", seq}, {"seq", seq}, {"types", Json::object()}});
        auto &marker = markers[found.first->second];
        marker["endSeq"] = seq;
        auto key = std::to_string(type);
        marker["types"][key] = marker["types"].value(key, 0) + 1;
    };
    if (needle.empty() && !hide) {
        auto &starts = array("fs_start");
        auto &lengths = array("fs_count");
        auto &func = array("fs_func");
        uint64_t begin = ordinal_before(lo), end = ordinal_before(hi + 1);
        std::vector<uint64_t> bounds_(bins + 1);
        for (size_t b = 0; b <= bins; ++b)
            bounds_[b] = ordinal_before(lo + (b * span + bins - 1) / bins);
        size_t p = starts.upper(begin);
        if (p)
            --p;
        size_t bin = 0;
        for (; p < starts.count() && uint64_t(starts.at(p)) < end; ++p) {
            uint64_t start = std::max<uint64_t>(starts.at(p), begin),
                     stop = std::min<uint64_t>(starts.at(p) + lengths.at(p), end);
            while (bin < bins && bounds_[bin + 1] <= start)
                ++bin;
            size_t b = bin;
            while (b < bins && bounds_[b] < stop) {
                auto n = std::min(stop, bounds_[b + 1]) - std::max(start, bounds_[b]);
                counts[b * fsize + func.at(p)] += n;
                ++b;
            }
        }
        for (const auto &spec : std::vector<std::pair<std::string, std::vector<int64_t> *>>{
                 {"unknown", &unknown}, {"not_taken", &not_taken}}) {
            auto &seq = array(spec.first + "_seq");
            auto &fn = array(spec.first + "_func");
            for (size_t i = seq.lower(lo), e = seq.upper(hi); i < e; ++i) {
                auto b = std::min<uint64_t>(bins - 1, (seq.at(i) - lo) * bins / span);
                ++spec.second->at(b);
                --counts[b * fsize + fn.at(i)];
            }
        }
        auto &ev = array("ev_seq");
        auto &type = array("ev_type");
        for (size_t i = ev.lower(lo), e = ev.upper(hi); i < e; ++i)
            add_marker(ev.at(i), type.at(i));
        filtered = span;
    } else {
        auto matching = match_static(needle);
        auto &fn = array("st_func");
        rows(lo, hi, [&](const NativeRow &r) {
            if (r.type) {
                if (!needle.empty() &&
                    clean_search("    " + r.event.at("text").get<std::string>()).find(needle) ==
                        std::string::npos)
                    return true;
                ++filtered;
                add_marker(r.seq, r.type);
                return true;
            }
            if ((hide && r.state == 1) || !matching[r.id])
                return true;
            ++filtered;
            auto b = std::min<uint64_t>(bins - 1, (r.seq - lo) * bins / span);
            if (r.state == 0)
                ++counts[b * fsize + fn.at(r.id)];
            else if (r.state == 1)
                ++not_taken[b];
            else
                ++unknown[b];
            return true;
        });
    }
    for (size_t b = 0; b < bins; ++b)
        for (size_t f = 0; f < fsize; ++f)
            totals[f] += counts[b * fsize + f];
    std::vector<size_t> order(fsize);
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
        return std::make_pair(-totals[a], functions[a]) < std::make_pair(-totals[b], functions[b]);
    });
    std::vector<bool> top(fsize, false);
    Json lanes = Json::array();
    for (size_t i = 0; i < std::min(max_functions, fsize); ++i)
        if (totals[order[i]] > 0) {
            auto f = order[i];
            top[f] = true;
            std::vector<int64_t> values(bins);
            for (size_t b = 0; b < bins; ++b)
                values[b] = counts[b * fsize + f];
            lanes.push_back(Json{{"key", "fn:" + functions[f]},
                                 {"name", functions[f]},
                                 {"kind", "function"},
                                 {"records", totals[f]},
                                 {"bins", values}});
        }
    auto lane = [&](const char *key, const char *name, const char *kind,
                    const std::vector<int64_t> &values) {
        auto n = std::accumulate(values.begin(), values.end(), int64_t(0));
        if (n)
            lanes.push_back(Json{
                {"key", key}, {"name", name}, {"kind", kind}, {"records", n}, {"bins", values}});
    };
    std::vector<int64_t> other(bins, 0);
    for (size_t b = 0; b < bins; ++b)
        for (size_t f = 0; f < fsize; ++f)
            if (!top[f])
                other[b] += counts[b * fsize + f];
    lane("other", "其他函数", "other", other);
    lane("unknown", "执行状态未知", "unknown", unknown);
    if (!hide)
        lane("not-taken", "未成立路径（未证实执行）", "not-taken", not_taken);
    for (auto &marker : markers) {
        int n = 0;
        for (const auto &t : marker["types"])
            n += t.get<int>();
        marker["count"] = n;
    }
    return Json{
        {"range", Json{{"start", lo}, {"end", hi}, {"totalStart", first}, {"totalEnd", last}}},
        {"lanes", lanes},
        {"binCount", bins},
        {"markers", markers},
        {"markerCount", marker_count},
        {"summary",
         Json{{"executed", std::accumulate(totals.begin(), totals.end(), int64_t(0))},
              {"unknown", std::accumulate(unknown.begin(), unknown.end(), int64_t(0))},
              {"notTaken", std::accumulate(not_taken.begin(), not_taken.end(), int64_t(0))},
              {"filteredRecords", filtered},
              {"markers", marker_count}}},
        {"timing", Json{{"axis", "execution-order"},
                        {"verifiedTime", false},
                        {"reason", "当前记录没有已验收的逐指令时间戳，横轴只表示执行序号"}}}};
}

Json NativeStore::navigate(const Json &request) {
    int64_t seq = request.value("seq", int64_t(0));
    bool forward = request.value("direction", int64_t(1)) > 0;
    auto mode = request.value("mode", std::string("instruction"));
    if (mode != "instruction" && mode != "call" && mode != "return" && mode != "exception" &&
        mode != "issue" && mode != "source")
        fail(kExitInput, "未知导航类型");
    auto scoped = bounds(request);
    auto lo = scoped.first, hi = scoped.second;
    auto answer = [](Json seq_, bool wrap = false) {
        return Json{{"seq", seq_}, {"wrapped", wrap}};
    };
    if (hi < lo)
        return answer(nullptr);
    if (request.contains("pc") && !request["pc"].is_null()) {
        uint64_t target = request.at("pc");
        int64_t sid = -1;
        for (size_t i = 0; i < static_rows.size(); ++i)
            if (static_rows[i].at("pc") == target) {
                sid = i;
                break;
            }
        if (sid < 0)
            return answer(nullptr);
        auto &offsets = array("pc_cell_offsets");
        auto &cells = array("pc_cells");
        auto &anchors = array("cell_first_seq");
        int64_t found = -1;
        auto scan = [&](bool direction, int64_t from, int64_t until) {
            size_t begin = offsets.at(sid), end = offsets.at(sid + 1);
            for (size_t p = direction ? begin : end; p != (direction ? end : begin);) {
                size_t i = direction ? p++ : --p;
                uint64_t cell = cells.at(i), a = anchors.at(cell),
                         b = cell + 1 < anchors.count() ? uint64_t(anchors.at(cell + 1)) - 1 : last;
                if (b < uint64_t(std::max<int64_t>(0, std::min(from, until))) ||
                    a > uint64_t(std::max(from, until)))
                    continue;
                int64_t result = -1;
                rows(std::max<int64_t>(a, std::min(from, until)),
                     std::min<int64_t>(b, std::max(from, until)), [&](const NativeRow &r) {
                         if (!r.type && r.id == uint32_t(sid)) {
                             result = r.seq;
                             return !direction;
                         }
                         return true;
                     });
                if (result >= 0)
                    return result;
            }
            return int64_t(-1);
        };
        if (forward && std::max(seq + 1, lo) <= hi)
            found = scan(true, std::max(seq + 1, lo), hi);
        else if (!forward && std::min(seq - 1, hi) >= lo)
            found = scan(false, std::min(seq - 1, hi), lo);
        if (found >= 0)
            return answer(found);
        found = scan(true, lo, hi);
        return found >= 0 ? answer(found, true) : answer(nullptr);
    }
    if (mode == "instruction") {
        int64_t found = forward ? int64_t(next_instruction(std::max(seq + 1, lo)))
                                : previous_instruction(std::min(seq - 1, hi));
        return found >= lo && found <= hi ? answer(found) : answer(nullptr);
    }
    if (mode == "source") {
        std::string file;
        int64_t line = 0;
        if (seq >= int64_t(first) && seq <= int64_t(last) && !is_event(seq)) {
            auto current = event(seq).at("event");
            if (!current.at("file").is_null())
                file = current.at("file");
            if (!current.at("line").is_null())
                line = current.at("line");
        }
        auto &starts = array("line_start");
        auto &ids = array("line_id");
        int64_t initial = forward ? int64_t(next_instruction(std::max(seq + 1, lo)))
                                  : previous_instruction(std::min(seq - 1, hi));
        if (initial < lo || initial > hi)
            return answer(nullptr);
        uint64_t ordinal = ordinal_before(initial);
        size_t p = starts.upper(ordinal);
        if (p)
            --p;
        while (p < starts.count()) {
            uint64_t begin = starts.at(p), end = p + 1 < starts.count()
                                                     ? uint64_t(starts.at(p + 1)) - 1
                                                     : instructions - 1;
            auto &entry = static_rows.at(ids.at(p));
            if (!entry.at("line").is_null() &&
                    (entry.value("file", Json("")).is_null()
                         ? std::string()
                         : entry.at("file").get<std::string>()) != file ||
                !entry.at("line").is_null() && entry.at("line").get<int64_t>() != line) {
                uint64_t n = forward ? std::max(begin, ordinal) : std::min(end, ordinal),
                         s = seq_of(n);
                if (s >= uint64_t(lo) && s <= uint64_t(hi))
                    return answer(s);
            }
            if (forward) {
                ++p;
                if (p >= starts.count() || seq_of(starts.at(p)) > uint64_t(hi))
                    break;
            } else {
                if (!p || seq_of(begin) <= uint64_t(lo))
                    break;
                --p;
                ordinal = starts.at(p) +
                          (p + 1 < starts.count() ? starts.at(p + 1) - starts.at(p)
                                                  : instructions - starts.at(p)) -
                          1;
            }
        }
        return answer(nullptr);
    }
    unsigned nav_mode = mode == "call" ? 1 : mode == "return" ? 2 : mode == "exception" ? 3 : 4;
    std::vector<uint64_t> values;
    for (auto n : of_type(5)) {
        auto data = block(n);
        NativeCursor c(*data);
        auto kind = c.le(1), count = c.uv();
        uint64_t value = 0;
        for (size_t i = 0; i < count; ++i) {
            value += c.uv();
            if (kind == nav_mode)
                values.push_back(value);
        }
        if (c.pos != c.size)
            fail(kExitInput, "Navigation block has trailing bytes");
    }
    if (forward) {
        auto p = std::upper_bound(values.begin(), values.end(), std::max(seq, lo - 1));
        if (p != values.end() && *p <= uint64_t(hi))
            return answer(*p);
    } else {
        auto p = std::lower_bound(values.begin(), values.end(), std::min(seq, hi + 1));
        if (p != values.begin() && *--p >= uint64_t(lo))
            return answer(*p);
    }
    return answer(nullptr);
}
