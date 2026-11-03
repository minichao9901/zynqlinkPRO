// Immutable ARM ELF snapshot, DWARF line tables and Capstone Thumb dictionary.
// All address, predicate and flow interpretation stays in this native module.
#pragma once
std::string native_utf8_replace(const std::string &input) {
    std::string out;
    size_t i = 0;
    while (i < input.size()) {
        uint8_t first = input[i];
        if (first < 128) {
            out += input[i++];
            continue;
        }
        size_t n = first >= 0xc2 && first <= 0xdf   ? 2
                   : first >= 0xe0 && first <= 0xef ? 3
                   : first >= 0xf0 && first <= 0xf4 ? 4
                                                    : 0;
        if (!n) {
            out += "\xef\xbf\xbd";
            ++i;
            continue;
        }
        size_t valid = 1;
        while (valid < n && i + valid < input.size()) {
            uint8_t b = input[i + valid];
            if (b < 0x80 || b > 0xbf ||
                valid == 1 && (first == 0xe0 && b < 0xa0 || first == 0xed && b >= 0xa0 ||
                               first == 0xf0 && b < 0x90 || first == 0xf4 && b >= 0x90))
                break;
            ++valid;
        }
        if (valid == n)
            out.append(input, i, n);
        else
            out += "\xef\xbf\xbd";
        i += valid;
    }
    return out;
}
struct NativeImage {
    struct Segment {
        uint32_t address, physical, flags, offset, size, memory;
    };
    struct Section {
        std::string name;
        uint32_t type, flags, address, offset, size, link, info, align, entry;
        std::vector<uint8_t> data;
    };
    struct Function {
        uint32_t address, size;
        std::string name;
    };
    struct Line {
        uint64_t end;
        std::string file;
        uint64_t number;
    };
    std::vector<uint8_t> bytes;
    std::vector<Segment> segments;
    std::vector<Section> sections;
    std::vector<Function> functions;
    std::map<uint64_t, Line> lines;
    std::set<uint64_t> predicates, known;
    std::string sha;
    csh decoder = 0;
    double parse_seconds = 0, static_seconds = 0;
    static void need(bool b, const char *message) {
        if (!b)
            fail(kExitInput, message);
    }
    uint64_t number(size_t offset, size_t width) const {
        need(offset <= bytes.size() && width <= bytes.size() - offset, "ELF field exceeds file");
        uint64_t v = 0;
        for (size_t i = 0; i < width; ++i)
            v |= uint64_t(bytes[offset + i]) << (8 * i);
        return v;
    }
    std::string string_at(size_t offset, size_t limit) const {
        need(offset <= limit && limit <= bytes.size(), "ELF string extent invalid");
        size_t end = offset;
        while (end < limit && bytes[end])
            ++end;
        need(end < limit, "Unterminated ELF string");
        return native_utf8_replace(
            std::string(reinterpret_cast<const char *>(bytes.data() + offset), end - offset));
    }
    static std::string path_join(const std::string &directory, const std::string &file) {
        fs::path joined = fs::u8path(native_utf8_replace(directory)) /
                          fs::u8path(native_utf8_replace(file)),
                 clean;
        for (const auto &part : joined)
            if (part != fs::path("."))
                clean /= part;
        return clean.generic_u8string();
    }
    NativeImage(const std::string &path) {
        const auto started = std::chrono::steady_clock::now();
        std::ifstream input(file_path(path), std::ios::binary | std::ios::ate);
        need(bool(input), "Cannot open target ELF");
        auto size = input.tellg();
        need(size >= 52 && uint64_t(size) <= (512ull << 20), "ELF size invalid");
        bytes.resize(size);
        input.seekg(0);
        need(bool(input.read(reinterpret_cast<char *>(bytes.data()), bytes.size())),
             "ELF read failed");
        FastSha256 hash;
        hash.update(bytes.data(), bytes.size());
        sha = hash.hex_digest();
        need(std::memcmp(bytes.data(),
                         "\x7f"
                         "ELF",
                         4) == 0 &&
                 bytes[4] == 1 && bytes[5] == 1 && number(18, 2) == 40,
             "Expected little-endian ARM ELF32");
        uint64_t shoff = number(32, 4), phoff = number(28, 4), shsize = number(46, 2),
                 phsize = number(42, 2), shnum = number(48, 2), shstr = number(50, 2),
                 phnum = number(44, 2);
        if (shoff && shsize >= 40) {
            if (!shnum)
                shnum = number(shoff + 20, 4);
            if (shstr == 65535)
                shstr = number(shoff + 24, 4);
            if (phnum == 65535)
                phnum = number(shoff + 28, 4);
        }
        need(shnum <= (1u << 20) && (!shnum || shsize >= 40 && shoff <= bytes.size() &&
                                                   shnum <= (bytes.size() - shoff) / shsize),
             "ELF section table invalid");
        need(phnum <= (1u << 20) && (!phnum || phsize >= 32 && phoff <= bytes.size() &&
                                                   phnum <= (bytes.size() - phoff) / phsize),
             "ELF program table invalid");
        for (size_t n = 0; n < phnum; ++n) {
            size_t p = phoff + n * phsize;
            if (number(p, 4) != 1 || !number(p + 16, 4))
                continue;
            Segment s{uint32_t(number(p + 8, 4)),  uint32_t(number(p + 12, 4)),
                      uint32_t(number(p + 24, 4)), uint32_t(number(p + 4, 4)),
                      uint32_t(number(p + 16, 4)), uint32_t(number(p + 20, 4))};
            need(s.offset <= bytes.size() && s.size <= bytes.size() - s.offset &&
                     uint64_t(s.address) + s.size <= 0x100000000ull,
                 "ELF load extent invalid");
            segments.push_back(s);
        }
        size_t strings_offset = 0, strings_size = 0;
        if (shnum) {
            need(shstr < shnum, "ELF section names index invalid");
            strings_offset = number(shoff + shstr * shsize + 16, 4);
            strings_size = number(shoff + shstr * shsize + 20, 4);
            need(strings_offset <= bytes.size() && strings_size <= bytes.size() - strings_offset,
                 "ELF section names extent invalid");
        }
        for (size_t n = 0; n < shnum; ++n) {
            size_t p = shoff + n * shsize;
            Section s;
            s.name = string_at(strings_offset + number(p, 4), strings_offset + strings_size);
            s.type = number(p + 4, 4);
            s.flags = number(p + 8, 4);
            s.address = number(p + 12, 4);
            s.offset = number(p + 16, 4);
            s.size = number(p + 20, 4);
            s.link = number(p + 24, 4);
            s.info = number(p + 28, 4);
            s.align = number(p + 32, 4);
            s.entry = number(p + 36, 4);
            need(s.type == 8 || s.offset <= bytes.size() && s.size <= bytes.size() - s.offset,
                 "ELF section exceeds file");
            if (s.name.rfind(".debug", 0) == 0 || s.name.rfind(".zdebug", 0) == 0) {
                need(s.type != 8, "DWARF section cannot be NOBITS");
                s.data.assign(bytes.begin() + s.offset, bytes.begin() + s.offset + s.size);
                size_t header = 0;
                uint64_t decoded = 0;
                if (s.flags & 0x800) {
                    need(s.data.size() >= 12 && read_u32(s.data.data()) == 1,
                         "Unsupported ELF compression");
                    header = 12;
                    decoded = read_u32(s.data.data() + 4);
                    s.flags &= ~0x800u;
                } else if (s.name.rfind(".zdebug", 0) == 0) {
                    need(s.data.size() >= 12 && std::memcmp(s.data.data(), "ZLIB", 4) == 0,
                         "Invalid GNU compressed section");
                    header = 12;
                    for (size_t i = 4; i < 12; ++i)
                        decoded = (decoded << 8) | s.data[i];
                    s.name.replace(0, 7, ".debug");
                }
                if (header) {
                    need(decoded <= (256u << 20), "Inflated DWARF section exceeds limit");
                    std::vector<uint8_t> expanded(decoded);
                    uLongf length = decoded;
                    need(uncompress(expanded.data(), &length, s.data.data() + header,
                                    s.data.size() - header) == Z_OK &&
                             length == decoded,
                         "DWARF decompression failed");
                    s.data = std::move(expanded);
                    s.size = decoded;
                }
            }
            sections.push_back(std::move(s));
        }
        for (const auto &s : sections)
            if (s.name == ".symtab") {
                need(s.entry >= 16 && s.link < sections.size() && s.size % s.entry == 0,
                     "ELF symbol table invalid");
                const auto &names = sections[s.link];
                for (size_t i = 0; i < s.size; i += s.entry) {
                    size_t p = s.offset + i;
                    if ((bytes.at(p + 12) & 15) != 2 || !number(p + 8, 4))
                        continue;
                    functions.push_back(Function{uint32_t(number(p + 4, 4) & ~uint64_t(1)),
                                                 uint32_t(number(p + 8, 4)),
                                                 string_at(names.offset + number(p, 4),
                                                           uint64_t(names.offset) + names.size)});
                }
            }
        std::sort(functions.begin(), functions.end(), [](const Function &a, const Function &b) {
            return std::tie(a.address, a.size, a.name) < std::tie(b.address, b.size, b.name);
        });
        parse_lines();
        need(cs_open(CS_ARCH_ARM, cs_mode(CS_MODE_THUMB | CS_MODE_MCLASS), &decoder) == CS_ERR_OK,
             "Cannot initialize native Capstone");
        need(cs_option(decoder, CS_OPT_DETAIL, CS_OPT_ON) == CS_ERR_OK,
             "Cannot enable Capstone detail");
        parse_seconds = chrono_seconds(started);
    }
    ~NativeImage() {
        if (decoder)
            cs_close(&decoder);
    }
    NativeImage(const NativeImage &) = delete;
    NativeImage &operator=(const NativeImage &) = delete;
    std::pair<const uint8_t *, size_t> read(uint64_t address, size_t length) const {
        for (const auto &s : segments)
            if (address >= s.address && address < uint64_t(s.address) + s.size) {
                const auto available =
                    std::min<uint64_t>(length, uint64_t(s.address) + s.size - address);
                return {bytes.data() + s.offset + address - s.address, size_t(available)};
            }
        return {nullptr, 0};
    }
    std::tuple<std::string, std::string, int64_t> location(uint64_t pc) const {
        std::string fn, file;
        int64_t line = -1;
        auto f = std::upper_bound(functions.begin(), functions.end(), pc,
                                  [](uint64_t p, const Function &v) { return p < v.address; });
        if (f != functions.begin()) {
            --f;
            if (pc < uint64_t(f->address) + f->size)
                fn = f->name;
        }
        auto l = lines.upper_bound(pc);
        if (l != lines.begin()) {
            --l;
            if (pc < l->second.end) {
                file = l->second.file;
                line = l->second.number;
            }
        }
        return {fn, file, line};
    }
    static int section_info(void *object, Dwarf_Unsigned index, Dwarf_Obj_Access_Section_a *value,
                            int *) {
        auto &self = *static_cast<NativeImage *>(object);
        if (index >= self.sections.size())
            return DW_DLV_NO_ENTRY;
        const auto &s = self.sections[index];
        *value = {s.name.c_str(), s.type, s.flags, s.address, s.offset,
                  s.size,         s.link, s.info,  s.align,   s.entry};
        return DW_DLV_OK;
    }
    static Dwarf_Small byte_order(void *) { return DW_END_little; }
    static Dwarf_Small four(void *) { return 4; }
    static Dwarf_Unsigned filesize(void *object) {
        return static_cast<NativeImage *>(object)->bytes.size();
    }
    static Dwarf_Unsigned section_count(void *object) {
        return static_cast<NativeImage *>(object)->sections.size();
    }
    static int load_section(void *object, Dwarf_Unsigned index, Dwarf_Small **data, int *error) {
        auto &self = *static_cast<NativeImage *>(object);
        if (index >= self.sections.size())
            return DW_DLV_NO_ENTRY;
        const auto &s = self.sections[index];
        if (!s.size)
            return DW_DLV_NO_ENTRY;
        *data = static_cast<Dwarf_Small *>(std::malloc(s.size));
        if (!*data) {
            *error = DW_DLE_MAF;
            return DW_DLV_ERROR;
        }
        std::memcpy(*data, s.data.empty() ? self.bytes.data() + s.offset : s.data.data(), s.size);
        return DW_DLV_OK;
    }
    void parse_lines() {
        bool present = false;
        for (const auto &s : sections)
            present |= s.name == ".debug_info";
        if (!present)
            return;
        Dwarf_Obj_Access_Methods_a methods{};
        methods.om_get_section_info = section_info;
        methods.om_get_byte_order = byte_order;
        methods.om_get_length_size = four;
        methods.om_get_pointer_size = four;
        methods.om_get_filesize = filesize;
        methods.om_get_section_count = section_count;
        methods.om_load_section = load_section;
        Dwarf_Obj_Access_Interface_a object{this, &methods};
        Dwarf_Debug dbg = nullptr;
        Dwarf_Error err = nullptr;
        auto check = [&](int code, const char *operation) {
            if (code == DW_DLV_ERROR) {
                std::string message =
                    std::string(operation) + ": " + (err ? dwarf_errmsg(err) : "DWARF error");
                if (err)
                    dwarf_dealloc_error(dbg, err);
                err = nullptr;
                fail(kExitInput, message);
            }
            return code;
        };
        if (check(dwarf_object_init_b(&object, nullptr, nullptr, DW_GROUPNUMBER_ANY, &dbg, &err),
                  "DWARF init") != DW_DLV_OK)
            return;
        struct Close {
            Dwarf_Debug dbg;
            ~Close() { dwarf_object_finish(dbg); }
        } close{dbg};
        while (true) {
            Dwarf_Unsigned length = 0, next = 0, typeoff = 0;
            Dwarf_Half version = 0, addrsize = 0, len = 0, extension = 0, type = 0;
            Dwarf_Off abbrev = 0;
            Dwarf_Sig8 sig{};
            if (check(dwarf_next_cu_header_d(dbg, true, &length, &version, &abbrev, &addrsize, &len,
                                             &extension, &sig, &typeoff, &next, &type, &err),
                      "DWARF CU") != DW_DLV_OK)
                break;
            Dwarf_Die cu = nullptr;
            check(dwarf_siblingof_b(dbg, nullptr, true, &cu, &err), "DWARF CU DIE");
            if (!cu)
                continue;
            struct DieClose {
                Dwarf_Die die;
                ~DieClose() { dwarf_dealloc_die(die); }
            } die_close{cu};
            Dwarf_Line_Context context = nullptr;
            Dwarf_Unsigned lineversion = 0;
            Dwarf_Small tables = 0;
            if (check(dwarf_srclines_b(cu, &lineversion, &tables, &context, &err), "DWARF lines") !=
                DW_DLV_OK)
                continue;
            struct LinesClose {
                Dwarf_Line_Context c;
                ~LinesClose() { dwarf_srclines_dealloc_b(c); }
            } lines_close{context};
            const char *compdir = nullptr;
            check(dwarf_srclines_comp_dir(context, &compdir, &err), "DWARF directory");
            std::string directory = compdir ? compdir : "";
            Dwarf_Signed base = 0, count = 0, end = 0;
            check(dwarf_srclines_files_indexes(context, &base, &count, &end, &err), "DWARF files");
            need(count >= 0 && count <= (1 << 20), "DWARF file count exceeds limit");
            std::map<uint64_t, std::string> files;
            for (auto i = base; i < end; ++i) {
                const char *name = nullptr;
                Dwarf_Unsigned dir = 0;
                check(dwarf_srclines_files_data_b(context, i, &name, &dir, nullptr, nullptr,
                                                  nullptr, &err),
                      "DWARF filename");
                std::string d = directory;
                if (dir || lineversion >= 5) {
                    const char *include = nullptr;
                    check(dwarf_srclines_include_dir_data(context, dir, &include, &err),
                          "DWARF include directory");
                    d = include ? include : "";
                    if (!fs::u8path(d).is_absolute())
                        d = path_join(directory, d);
                }
                files[i] = path_join(d, name ? name : "");
            }
            Dwarf_Line *rows = nullptr;
            Dwarf_Signed rows_count = 0;
            check(dwarf_srclines_from_linecontext(context, &rows, &rows_count, &err),
                  "DWARF line rows");
            need(rows_count >= 0 && rows_count <= (1 << 24), "DWARF line count exceeds limit");
            bool previous = false;
            Dwarf_Addr previous_address = 0;
            Dwarf_Unsigned previous_line = 0, previous_file = 0;
            for (Dwarf_Signed i = 0; i < rows_count; ++i) {
                Dwarf_Addr address = 0;
                Dwarf_Unsigned line = 0, file = 0;
                Dwarf_Bool last = false;
                check(dwarf_lineaddr(rows[i], &address, &err), "DWARF line address");
                check(dwarf_lineno(rows[i], &line, &err), "DWARF line number");
                check(dwarf_line_srcfileno(rows[i], &file, &err), "DWARF line file");
                check(dwarf_lineendsequence(rows[i], &last, &err), "DWARF end sequence");
                need(address <= UINT32_MAX && line <= INT32_MAX, "DWARF line exceeds ARM32/store bounds");
                if (previous && address > previous_address && previous_line)
                    lines[previous_address] = Line{address, files[previous_file], previous_line};
                previous = !last;
                previous_address = address;
                previous_line = line;
                previous_file = file;
            }
        }
    }
    void prepare_addresses() {
        for (const auto &f : functions) {
            auto data = read(f.address, f.size);
            cs_insn *instructions = nullptr;
            size_t count = cs_disasm(decoder, data.first, data.second, f.address, 0, &instructions);
            unsigned remaining = 0;
            for (size_t i = 0; i < count; ++i) {
                auto &ins = instructions[i];
                known.insert(ins.address);
                if (ins.id == ARM_INS_IT)
                    remaining = std::strlen(ins.mnemonic) - 1;
                else if (remaining) {
                    predicates.insert(ins.address);
                    --remaining;
                }
            }
            cs_free(instructions, count);
        }
    }
    bool predicate(uint64_t pc) {
        if (known.count(pc))
            return predicates.count(pc);
        for (uint64_t start = pc > 18 ? pc - 18 : 0; start < pc; start += 2) {
            auto data = read(start, pc - start + 4);
            cs_insn *list = nullptr;
            size_t count = cs_disasm(decoder, data.first, data.second, start, 0, &list);
            bool found = false;
            if (count && list[0].id == ARM_INS_IT) {
                auto slots = std::strlen(list[0].mnemonic) - 1;
                for (size_t n = 1; n < std::min<size_t>(count, slots + 1); ++n)
                    found |= list[n].address == pc;
            }
            cs_free(list, count);
            if (found)
                return true;
        }
        return false;
    }
    StaticDict dictionary(const std::vector<RangeRecord> &ranges) {
        const auto started = std::chrono::steady_clock::now();
        prepare_addresses();
        StaticDict dict;
        dict.version = 1;
        dict.has_extension = true;
        dict.elf_sha256 = sha;
        dict.strings.push_back("");
        std::map<uint32_t, StaticEntry> entries;
        for (const auto &range : ranges) {
            auto data = read(range.start, range.end - range.start);
            cs_insn *list = nullptr;
            size_t count = cs_disasm(decoder, data.first, data.second, range.start, 0, &list);
            struct Free {
                cs_insn *p;
                size_t n;
                ~Free() { cs_free(p, n); }
            } free{list, count};
            need(count == range.payload && count &&
                     list[count - 1].address + list[count - 1].size == range.end,
                 "Capstone range differs from OpenCSD");
            for (size_t i = 0; i < count; ++i) {
                const auto &ins = list[i];
                if (entries.count(ins.address))
                    continue;
                StaticEntry e;
                e.pc = ins.address;
                e.size = ins.size;
                e.id = entries.size();
                e.code_bytes = e.size;
                need(e.size <= 16, "Native instruction exceeds dictionary field");
                std::memcpy(e.code, ins.bytes, e.size);
                auto location_ = location(e.pc);
                const auto &fn = std::get<0>(location_);
                const auto &file = std::get<1>(location_);
                e.line = std::get<2>(location_);
                e.flags = 1 | 2 | 4 | (e.line >= 0 ? 8 : 0);
                e.text_slots = 4;
                e.text_base = dict.strings.size();
                dict.strings.insert(dict.strings.end(), {fn, file, ins.mnemonic, ins.op_str});
                cs_insn *single = nullptr;
                size_t one = cs_disasm(decoder, ins.bytes, ins.size, ins.address, 1, &single);
                struct SingleFree {
                    cs_insn *p;
                    size_t n;
                    ~SingleFree() { cs_free(p, n); }
                } single_free{single, one};
                e.flow = kFlowUnknown;
                e.conditional = 1;
                if (one) {
                    const auto &s = single[0];
                    std::string mnemonic = s.mnemonic, operands = s.op_str;
                    e.conditional =
                        s.detail->arm.cc != ARM_CC_AL && s.detail->arm.cc != ARM_CC_INVALID;
                    if (s.id == ARM_INS_BL || s.id == ARM_INS_BLX)
                        e.flow = kFlowCall;
                    else if (mnemonic.rfind("bx", 0) == 0 ||
                             ((mnemonic.rfind("pop", 0) == 0 || mnemonic.rfind("ldm", 0) == 0) &&
                              operands.find("pc") != std::string::npos))
                        e.flow = operands.find("lr") != std::string::npos ||
                                         operands.find("pc") != std::string::npos
                                     ? kFlowReturn
                                     : kFlowBranch;
                    else {
                        bool branch = cs_insn_group(decoder, &s, CS_GRP_JUMP);
                        cs_regs reads, writes;
                        uint8_t nr = 0, nw = 0;
                        need(cs_regs_access(decoder, &s, reads, &nr, writes, &nw) == CS_ERR_OK,
                             "Cannot inspect instruction flow");
                        for (size_t n = 0; n < nw; ++n)
                            branch |= writes[n] == ARM_REG_PC;
                        e.flow = branch ? kFlowBranch : kFlowLinear;
                    }
                }
                e.predicated = e.flow == kFlowLinear && predicate(e.pc);
                entries.emplace(e.pc, e);
            }
        }
        for (auto &item : entries) {
            dict.by_pc[item.first] = dict.entries.size();
            dict.entries.push_back(item.second);
        }
        auto previous_strings = std::move(dict.strings);
        dict.strings = {""};
        for (auto &e : dict.entries) {
            uint32_t old = e.text_base;
            e.text_base = dict.strings.size();
            for (int slot = 0; slot < 4; ++slot)
                dict.strings.push_back(previous_strings.at(old + slot));
        }
        dict.entry_count = dict.entries.size();
        dict.string_count = dict.strings.size();
        std::ostringstream pool(std::ios::binary);
        for (const auto &s : dict.strings) {
            write_u32(pool, s.size());
            pool.write(s.data(), s.size());
        }
        const auto pool_bytes = pool.str();
        dict.table_offset = 61 + pool_bytes.size();
        std::ostringstream packed(std::ios::binary);
        packed.write("R2STATIC1", 9);
        write_u32(packed, 1);
        for (size_t i = 0; i < sha.size(); i += 2)
            packed.put(char(std::stoul(sha.substr(i, 2), nullptr, 16)));
        write_u32(packed, dict.entry_count);
        write_u32(packed, dict.string_count);
        write_u64(packed, dict.table_offset);
        packed.write(pool_bytes.data(), pool_bytes.size());
        for (const auto &e : dict.entries) {
            uint8_t row[16] = {};
            std::memcpy(row, &e.pc, 4);
            row[4] = e.size;
            std::memcpy(row + 5, &e.id, 4);
            row[9] = e.predicated;
            row[10] = e.flow;
            packed.write(reinterpret_cast<const char *>(row), 16);
        }
        packed.write("R2EXT01\0", 8);
        write_u32(packed, 1);
        write_u32(packed, dict.entry_count);
        for (const auto &e : dict.entries) {
            uint8_t row[24] = {};
            std::memcpy(row, &e.line, 4);
            row[4] = e.conditional;
            row[5] = e.flags;
            std::memcpy(row + 6, e.code, e.code_bytes);
            packed.write(reinterpret_cast<const char *>(row), 24);
        }
        const auto canonical = packed.str();
        FastSha256 hash;
        hash.update(canonical.data(), canonical.size());
        dict.sha256 = hash.hex_digest();
        dict.bytes = canonical.size();
        static_seconds = chrono_seconds(started);
        return dict;
    }
    Json materialize(const fs::path &record, const Json &config, std::string &config_path) const {
        const bool v3 = config.at("protocol") == "ETMv3";
        std::ostringstream text;
        if (v3)
            text << "ETMv3\n";
        const std::vector<std::string> keys =
            v3 ? std::vector<std::string>{"idr", "ctrl", "ccer", "traceid"}
               : std::vector<std::string>{"idr0",  "idr1",  "idr2",  "idr8",   "idr9",   "idr10",
                                          "idr11", "idr12", "idr13", "config", "traceid"};
        for (const auto &key : keys)
            text << "0x" << std::hex << config.at(key).get<uint32_t>() << "\n";
        Json hashes = Json::object();
        size_t n = 0;
        for (const auto &s : segments) {
            auto path = (record / ("image-" + std::to_string(n++) + ".bin")).u8string();
            std::ofstream out(file_path(path), std::ios::binary);
            need(bool(out.write(reinterpret_cast<const char *>(bytes.data() + s.offset), s.size)),
                 "Cannot write native ELF segment");
            out.close();
            need(bool(out), "Cannot close native ELF segment");
            text << "0x" << std::hex << s.address << " "
                 << fs::absolute(fs::u8path(path)).u8string() << "\n";
            FastSha256 hash;
            hash.update(bytes.data() + s.offset, s.size);
            hashes[fs::absolute(fs::u8path(path)).u8string()] = hash.hex_digest();
        }
        config_path = fs::absolute(record / "native-config.txt").u8string();
        const auto data = text.str();
        std::ofstream out(file_path(config_path), std::ios::binary);
        need(bool(out.write(data.data(), data.size())), "Cannot write native decoder config");
        out.close();
        need(bool(out), "Cannot close native decoder config");
        FastSha256 hash;
        hash.update(data.data(), data.size());
        hashes[config_path] = hash.hex_digest();
        return hashes;
    }
    Json select_sources(const StaticDict &dict, const Json &snapshot,
                        const fs::path &allowed) const {
        std::set<std::string> names;
        for (const auto &e : dict.entries)
            if (!dict.text(e, 1).empty())
                names.insert(dict.text(e, 1));
        Json result = Json::object();
        for (const auto &name : names) {
            if (snapshot.contains(name)) {
                result[name] = snapshot[name];
                continue;
            }
            std::error_code ec;
            auto path = fs::weakly_canonical(fs::u8path(name), ec),
                 base = fs::weakly_canonical(allowed, ec);
            const auto relative = path.lexically_relative(base);
            bool inside = !ec && !relative.empty() && *relative.begin() != fs::path("..");
            if (inside && fs::is_regular_file(path)) {
                std::ifstream input(path, std::ios::binary);
                std::string text((std::istreambuf_iterator<char>(input)), {});
                if (text.compare(0, 3, "\xef\xbb\xbf") == 0)
                    text.erase(0, 3);
                result[name] = native_utf8_replace(text);
                continue;
            }
            std::string value;
            size_t matches = 0;
            std::string normalized = name;
            std::replace(normalized.begin(), normalized.end(), '\\', '/');
            for (auto it = snapshot.begin(); it != snapshot.end(); ++it) {
                auto key = it.key();
                std::replace(key.begin(), key.end(), '\\', '/');
                const auto suffix = "/" + key;
                if (normalized.size() >= suffix.size() &&
                    normalized.compare(normalized.size() - suffix.size(), suffix.size(), suffix) ==
                        0) {
                    value = it.value().get<std::string>();
                    ++matches;
                }
            }
            result[name] = matches == 1 ? value : "";
        }
        return result;
    }
    Json info(bool include_data = false) const {
        Json value{{"sha256", sha},
                   {"functions", Json::array()},
                   {"lines", Json::array()},
                   {"segments", Json::array()}};
        for (const auto &f : functions)
            value["functions"].push_back(Json::array({f.address, f.size, f.name}));
        for (const auto &l : lines)
            value["lines"].push_back(
                Json::array({l.first, l.second.end, l.second.file, l.second.number}));
        for (const auto &s : segments) {
            Json v{{"address", s.address},
                   {"physical", s.physical},
                   {"flags", s.flags},
                   {"size", s.size},
                   {"memory", s.memory}};
            if (include_data) {
                std::string hex;
                static const char *digits = "0123456789abcdef";
                hex.reserve(s.size * 2);
                for (size_t i = s.offset; i < size_t(s.offset) + s.size; ++i) {
                    hex += digits[bytes[i] >> 4];
                    hex += digits[bytes[i] & 15];
                }
                v["data"] = std::move(hex);
            }
            value["segments"].push_back(std::move(v));
        }
        return value;
    }
    Json elf_info(const std::string &filename) const {
        std::vector<Segment> flash;
        for (const auto &s : segments)
            if (s.physical >= 0x08000000 && s.physical < 0x08200000 && s.size)
                flash.push_back(s);
        if (flash.empty())
            fail(kExitInput, "当前调试支持 STM32 内部 Flash 范围 0x08000000–0x08200000 的 ELF");
        for (const auto &s : flash)
            if (uint64_t(s.physical) + s.size > 0x08200000)
                fail(kExitInput, "ELF Flash段超出验收范围");
        for (const auto &s : segments)
            if (s.flags & 1 &&
                (s.address < 0x08000000 || uint64_t(s.address) + s.size > 0x08200000))
                fail(kExitInput, "当前验收范围限内部 Flash 执行代码；RAM/外部存储执行镜像尚未验收");
        std::set<std::string> files;
        for (const auto &l : lines)
            if (!l.second.file.empty())
                files.insert(l.second.file);
        Json function_rows = Json::array(), program = Json::array();
        std::map<std::string, uint32_t> addresses;
        for (const auto &f : functions) {
            addresses[f.name] = f.address;
            bool executable = false;
            for (const auto &s : segments)
                executable |= (s.flags & 1) && f.address >= s.address &&
                              uint64_t(f.address) < uint64_t(s.address) + s.size;
            if (executable) {
                auto loc = location(f.address);
                function_rows.push_back(
                    Json{{"name", f.name},
                         {"address", f.address},
                         {"size", f.size},
                         {"file", std::get<1>(loc)},
                         {"line", std::get<2>(loc) < 0 ? Json(nullptr) : Json(std::get<2>(loc))}});
            }
        }
        static const char *alphabet =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        for (const auto &s : flash) {
            std::string encoded;
            encoded.reserve((s.size + 2) / 3 * 4);
            for (size_t i = 0; i < s.size; i += 3) {
                uint32_t v = uint32_t(bytes[s.offset + i]) << 16;
                if (i + 1 < s.size)
                    v |= uint32_t(bytes[s.offset + i + 1]) << 8;
                if (i + 2 < s.size)
                    v |= bytes[s.offset + i + 2];
                encoded += alphabet[(v >> 18) & 63];
                encoded += alphabet[(v >> 12) & 63];
                encoded += i + 1 < s.size ? alphabet[(v >> 6) & 63] : '=';
                encoded += i + 2 < s.size ? alphabet[v & 63] : '=';
            }
            program.push_back(Json{{"address", s.physical}, {"data", encoded}});
        }
        Json entry = nullptr;
        for (const auto *key : {"spi_trace_ready", "trace_hook_entry", "trace_workload", "main"}) {
            auto found = addresses.find(key);
            if (found != addresses.end()) {
                entry = found->second;
                break;
            }
        }
        return Json{{"name", fs::u8path(filename).filename().u8string()},
                    {"sha256", sha},
                    {"sourceFiles", files},
                    {"functions", function_rows},
                    {"captureEntry", entry},
                    {"segments", program}};
    }
};
