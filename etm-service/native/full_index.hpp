// Complete query tables and default views from in-memory execution facts.
// Included inside storebuild's implementation namespace; no Python/NumPy ABI.
#pragma once
using Json = nlohmann::ordered_json;

// Match the public reader's existing UTF-8 JSON representation, including
// insertion order, separators and shortest-roundtrip binary64 formatting.
std::string python_float(double value) {
    if (!std::isfinite(value))
        fail(kExitConsistency, "Non-finite query value");
    char buffer[128];
    auto result =
        std::to_chars(buffer, buffer + sizeof(buffer), value, std::chars_format::scientific);
    if (result.ec != std::errc())
        fail(kExitConsistency, "Cannot encode query float");
    std::string text(buffer, result.ptr);
    const auto e = text.find('e');
    if (e != std::string::npos) {
        const int exponent = std::stoi(text.substr(e + 1));
        if (exponent >= -4 && exponent < 16) {
            std::string mantissa = text.substr(0, e), sign;
            if (mantissa[0] == '-') {
                sign = "-";
                mantissa.erase(0, 1);
            }
            const auto dot = mantissa.find('.');
            const int before = dot == std::string::npos ? int(mantissa.size()) : int(dot);
            if (dot != std::string::npos)
                mantissa.erase(dot, 1);
            const int point = before + exponent;
            if (point <= 0)
                text = sign + "0." + std::string(-point, '0') + mantissa;
            else if (point >= int(mantissa.size()))
                text = sign + mantissa + std::string(point - mantissa.size(), '0') + ".0";
            else
                text = sign + mantissa.substr(0, point) + "." + mantissa.substr(point);
        } else {
            std::string sign = exponent < 0 ? "-" : "+";
            std::string digits = std::to_string(std::abs(exponent));
            if (digits.size() < 2)
                digits.insert(0, 1, '0');
            text = text.substr(0, e) + "e" + sign + digits;
        }
    } else if (text.find('.') == std::string::npos)
        text += ".0";
    return text;
}

void python_json_append(std::string &out, const Json &value) {
    if (value.is_object()) {
        out += '{';
        bool first = true;
        for (auto it = value.begin(); it != value.end(); ++it) {
            if (!first)
                out += ", ";
            first = false;
            out += Json(it.key()).dump();
            out += ": ";
            python_json_append(out, it.value());
        }
        out += '}';
    } else if (value.is_array()) {
        out += '[';
        bool first = true;
        for (const auto &item : value) {
            if (!first)
                out += ", ";
            first = false;
            python_json_append(out, item);
        }
        out += ']';
    } else if (value.is_number_float())
        out += python_float(value.get<double>());
    else
        out += value.dump();
}
std::string python_json(const Json &value) {
    std::string out;
    python_json_append(out, value);
    return out;
}

struct CompleteIndexResult {
    std::vector<uint8_t> payload;
    Json meta, timings;
    uint64_t source_mapped = 0;
    uint32_t first_pc = 0;
};

class CompleteIndex {
    const StaticDict &dict;
    const std::vector<const StaticEntry *> &entries;
    ExecutionFacts &facts;
    const BuildOutput &output;
    uint64_t total, cells, node_count, hotspot_count;
    std::vector<std::string> functions{"(未知函数)"}, strings{""};
    std::map<std::string, int32_t> function_ids{{"(未知函数)", 0}}, string_ids{{"", 0}};
    std::vector<int16_t> st_func, h_func;
    std::vector<int32_t> st_hotspot, h_file, h_line, node_parent, node_label, node_function;
    std::vector<uint32_t> st_pc;
    std::vector<uint8_t> st_size, st_pred;
    std::vector<int8_t> st_flow;
    std::vector<std::vector<int32_t>> chains, children;
    std::vector<std::vector<std::string>> paths;
    std::vector<int64_t> node_first, function_first, function_counts, function_unknown,
        function_not_taken, function_calls, function_interrupts;
    std::vector<int64_t> hotspot_counts, hotspot_unknown, hotspot_cycles, hotspot_first;
    std::vector<int32_t> hotspot_first_id;
    std::vector<int64_t> node_value, node_self, node_value_cycles, node_self_cycles;
    std::vector<int64_t> cell_cycles, cell_cycle_runs, dense_self_cycles;
    std::vector<int32_t> dense_self;
    std::vector<int64_t> timeline_counts, timeline_unknown, timeline_not_taken;
    std::vector<V2Table> tables;
    uint64_t source_mapped = 0;

    int32_t intern(const std::string &text) {
        auto found = string_ids.find(text);
        if (found != string_ids.end())
            return found->second;
        if (strings.size() >= 0x7FFFFFFFu)
            fail(kExitConsistency, "Query strings overflow");
        int32_t id = static_cast<int32_t>(strings.size());
        strings.push_back(text);
        string_ids.emplace(text, id);
        return id;
    }
    std::string text(const StaticEntry &e, int slot) const { return dict.text(e, slot); }
    template <class T>
    void add(const std::string &name, uint8_t dtype, const std::vector<T> &values,
             uint64_t width = 0) {
        if (width && values.size() % width)
            fail(kExitConsistency, "Query shape mismatch");
        V2Table table{name,
                      dtype,
                      static_cast<uint8_t>(width ? 2 : 1),
                      width ? values.size() / width : values.size(),
                      width,
                      {}};
        table.raw.resize(values.size() * sizeof(T));
        if (!values.empty())
            std::memcpy(table.raw.data(), values.data(), table.raw.size());
        tables.push_back(std::move(table));
    }
    void add_json(const std::string &name, const Json &value, Json *defaults = nullptr,
                  int bins = 0) {
        const std::string encoded = python_json(value);
        add(name, 0, std::vector<uint8_t>(encoded.begin(), encoded.end()));
        if (defaults) {
            FastSha256 sha;
            sha.update(encoded.data(), encoded.size());
            *defaults =
                Json{{"bins", bins}, {"bytes", encoded.size()}, {"sha256", sha.hex_digest()}};
        }
    }
    static size_t matrix_size(uint64_t rows, uint64_t columns) {
        if (columns && rows > (size_t(-1) / sizeof(int64_t)) / columns)
            fail(kExitConsistency, "Query matrix size overflow");
        return static_cast<size_t>(rows * columns);
    }
    uint64_t ordinal_before(uint64_t seq) const {
        const auto &ev = facts.fact_events;
        return seq - (std::lower_bound(ev.begin(), ev.end(), seq,
                                       [](const ExecutionFacts::FactEvent &e, uint64_t n) {
                                           return e.seq < n;
                                       }) -
                      ev.begin());
    }
    Json range() const {
        return Json{{"start", 0},
                    {"end", output.events - 1},
                    {"totalStart", 0},
                    {"totalEnd", output.events - 1}};
    }
    void mappings() {
        st_func.resize(entries.size());
        st_hotspot.resize(entries.size());
        std::map<std::tuple<std::string, bool, std::string, bool, int64_t>, int32_t> hotspots;
        std::vector<const StaticEntry *> hotspot_entries;
        for (size_t id = 0; id < entries.size(); ++id) {
            const auto &e = *entries[id];
            const std::string name = facts.fact_function_text[id];
            auto fn = function_ids.emplace(name, static_cast<int32_t>(functions.size()));
            if (fn.second)
                functions.push_back(name);
            if (fn.first->second > 0x7FFF)
                fail(kExitConsistency, "Query function id overflow");
            st_func[id] = static_cast<int16_t>(fn.first->second);
            const bool has_file = dict.has_extension && (e.flags & 4),
                       has_line = dict.has_extension && (e.flags & 8);
            auto key = std::make_tuple(name, has_file, has_file ? text(e, 1) : std::string(),
                                       has_line, has_line ? e.line : 0);
            auto hs = hotspots.emplace(key, static_cast<int32_t>(hotspots.size()));
            if (hs.second) {
                hotspot_entries.push_back(&e);
                h_func.push_back(st_func[id]);
            }
            st_hotspot[id] = hs.first->second;
            if (uint32_t(st_hotspot[id]) != facts.hotspot_of_id[id])
                fail(kExitConsistency, "Query hotspot order differs");
            st_pc.push_back(e.pc);
            st_size.push_back(e.size);
            st_pred.push_back(e.predicated);
            st_flow.push_back(e.flow);
        }
        hotspot_count = h_func.size();
        const auto &nodes = facts.fact_path->nodes();
        chains.resize(node_count);
        children.resize(node_count);
        paths.resize(node_count);
        node_function.assign(node_count, -1);
        for (size_t n = 0; n < node_count; ++n) {
            const int32_t parent = nodes[n].first;
            if ((n == 0 && parent != -1) || (n && (parent < 0 || parent >= int64_t(n))))
                fail(kExitConsistency, "Invalid query path parent");
            node_parent.push_back(parent);
            const auto &label = facts.fact_labels.values.at(nodes[n].second);
            node_label.push_back(intern(label));
            if (n) {
                children[parent].push_back(n);
                chains[n] = chains[parent];
                paths[n] = paths[parent];
                paths[n].push_back(label);
                auto fn = function_ids.find(label);
                if (fn != function_ids.end())
                    node_function[n] = fn->second;
            }
            chains[n].push_back(n);
        }
        std::vector<int64_t> ev_seq, ev_flags, ev_payload;
        std::vector<uint8_t> ev_type;
        std::vector<int32_t> ev_next, ev_text;
        for (const auto &ev : facts.fact_events) {
            ev_seq.push_back(ev.seq);
            ev_flags.push_back(ev.flags);
            ev_payload.push_back(static_cast<int64_t>(ev.payload));
            ev_type.push_back(ev.type);
            ev_text.push_back(intern(facts.fact_event_texts.at(ev.text_id)));
            int32_t fn = -1;
            if (ev.next_func >= 0) {
                auto found = function_ids.find(facts.fact_labels.values.at(ev.next_func));
                if (found != function_ids.end())
                    fn = found->second;
            }
            ev_next.push_back(fn);
        }
        add("ev_seq", 7, ev_seq);
        add("ev_flags", 7, ev_flags);
        add("ev_payload", 7, ev_payload);
        add("ev_type", 0, ev_type);
        add("ev_next_func", 5, ev_next);
        add("ev_text", 5, ev_text);
        for (const auto *e : hotspot_entries) {
            h_file.push_back(dict.has_extension && (e->flags & 4) ? intern(text(*e, 1)) : -1);
            h_line.push_back(dict.has_extension && (e->flags & 8) ? e->line : -1);
        }
        add("st_func", 3, st_func);
        add("st_hotspot", 5, st_hotspot);
        add("st_flow", 1, st_flow);
        add("st_pc", 4, st_pc);
        add("st_size", 0, st_size);
        add("st_pred", 0, st_pred);
        add("h_func", 3, h_func);
        add("h_file", 5, h_file);
        add("h_line", 5, h_line);
        add("node_parent", 5, node_parent);
        add("node_label", 5, node_label);
    }
    void instruction_tables() {
        std::vector<int64_t> insn(cells, 4096), executed(cells), unknown(cells), not_taken(cells),
            first_seq;
        std::vector<int32_t> anchor_block;
        std::vector<int64_t> anchor_offset, anchor_skip;
        if (cells)
            insn.back() = total - (cells - 1) * 4096;
        for (size_t c = 0; c < cells; ++c) {
            unknown[c] = facts.cell_unknown[c];
            not_taken[c] = facts.cell_not_taken[c];
            executed[c] = insn[c] - unknown[c] - not_taken[c];
            const auto &run = facts.fact_runs.at(c);
            if (run.ordinal != c * 4096)
                fail(kExitConsistency, "Invalid query anchor");
            first_seq.push_back(run.seq);
            anchor_block.push_back(run.block);
            anchor_offset.push_back(run.offset);
            anchor_skip.push_back(run.skip);
        }
        add("cell_insn", 7, insn);
        add("cell_executed", 7, executed);
        add("cell_unknown", 7, unknown);
        add("cell_not_taken", 7, not_taken);
        add("cell_first_seq", 7, first_seq);
        add("cell_anchor_block", 5, anchor_block);
        add("cell_anchor_offset", 7, anchor_offset);
        add("cell_anchor_skip", 7, anchor_skip);
        std::vector<uint16_t> hs_count(facts.hotspot_counts.begin(), facts.hotspot_counts.end()),
            hs_unknown(facts.hotspot_unknown.begin(), facts.hotspot_unknown.end());
        add("cell_hotspot_count", 2, hs_count, hotspot_count);
        add("cell_hotspot_unknown", 2, hs_unknown, hotspot_count);
        add("cell_hotspot_first", 4, facts.hotspot_first, hotspot_count);
        const size_t fs = functions.size();
        function_counts.assign(fs, 0);
        function_unknown.assign(fs, 0);
        function_not_taken.assign(fs, 0);
        function_calls.assign(fs, 0);
        function_interrupts.assign(fs, 0);
        function_first.assign(fs, 1ll << 60);
        hotspot_counts.assign(hotspot_count, 0);
        hotspot_unknown.assign(hotspot_count, 0);
        hotspot_cycles.assign(hotspot_count, 0);
        hotspot_first.assign(hotspot_count, 1ll << 60);
        hotspot_first_id.assign(hotspot_count, -1);
        timeline_counts.assign(1600 * fs, 0);
        timeline_unknown.assign(1600 * fs, 0);
        timeline_not_taken.assign(1600 * fs, 0);
        std::vector<int64_t> fs_start;
        std::vector<int32_t> fs_count;
        std::vector<int16_t> fs_func;
        std::vector<int32_t> unknown_seq, not_taken_seq, call_seq;
        std::vector<int16_t> unknown_func, not_taken_func, call_func;
        size_t ev = 0;
        int32_t previous_fn = -1;
        uint64_t previous_seq = uint64_t(-1);
        for (uint64_t i = 0; i < total; ++i) {
            while (ev < facts.fact_events.size() && facts.fact_events[ev].seq - ev <= i)
                ++ev;
            const uint64_t seq = i + ev;
            const auto id = facts.fact_ids[i];
            const auto fn = st_func.at(id);
            const auto hs = st_hotspot[id];
            const auto state = facts.fact_states[i];
            ++function_counts[fn];
            function_first[fn] = std::min<int64_t>(function_first[fn], i);
            ++hotspot_counts[hs];
            hotspot_unknown[hs] += st_pred[id] != 0;
            if (hotspot_first_id[hs] < 0) {
                hotspot_first[hs] = i;
                hotspot_first_id[hs] = id;
            }
            const size_t bin = std::min<uint64_t>(1599, seq * 1600 / output.events),
                         key = bin * fs + fn;
            ++timeline_counts[key];
            if (state == 2) {
                unknown_seq.push_back(seq);
                unknown_func.push_back(fn);
                ++function_unknown[fn];
                ++timeline_unknown[key];
            } else if (state == 1) {
                not_taken_seq.push_back(seq);
                not_taken_func.push_back(fn);
                ++function_not_taken[fn];
                ++timeline_not_taken[key];
            }
            if (i && facts.fact_states[i - 1] == 0 && st_flow[facts.fact_ids[i - 1]] == kFlowCall &&
                seq == previous_seq + 1) {
                call_seq.push_back(previous_seq);
                call_func.push_back(fn);
                ++function_calls[fn];
            }
            if (fn != previous_fn) {
                fs_start.push_back(i);
                fs_count.push_back(0);
                fs_func.push_back(fn);
                previous_fn = fn;
            }
            ++fs_count.back();
            previous_seq = seq;
            const auto &entry = *entries[id];
            source_mapped += dict.has_extension && (entry.flags & 8) && entry.line != 0;
        }
        for (const auto &event : facts.fact_events)
            if (event.type == 9 && event.seq + 1 < output.events && event.next_func >= 0) {
                auto it = function_ids.find(facts.fact_labels.values.at(event.next_func));
                if (it != function_ids.end())
                    ++function_interrupts[it->second];
            }
        add("fs_start", 7, fs_start);
        add("fs_count", 5, fs_count);
        add("fs_func", 3, fs_func);
        add("unknown_seq", 5, unknown_seq);
        add("unknown_func", 3, unknown_func);
        add("not_taken_seq", 5, not_taken_seq);
        add("not_taken_func", 3, not_taken_func);
        add("call_pair_seq", 5, call_seq);
        add("call_pair_func", 3, call_func);
    }
    void path_cycle_tables() {
        std::vector<int64_t> ps_start, ps_count, ps_leaf;
        dense_self.assign(matrix_size(cells, node_count), 0);
        dense_self_cycles.assign(dense_self.size(), 0);
        node_first.assign(node_count, 1ll << 60);
        node_first[0] = 0;
        for (const auto &run : facts.fact_path_runs) {
            ps_start.push_back(run.start);
            ps_count.push_back(run.count);
            ps_leaf.push_back(run.leaf);
            for (auto node : chains.at(run.leaf))
                node_first[node] = std::min<int64_t>(node_first[node], run.start);
            uint64_t start = run.start, end = start + run.count;
            while (start < end) {
                const uint64_t cell = start / 4096, stop = std::min(end, (cell + 1) * 4096);
                dense_self[cell * node_count + run.leaf] += stop - start;
                start = stop;
            }
        }
        add("ps_start", 7, ps_start);
        add("ps_count", 7, ps_count);
        add("ps_leaf", 7, ps_leaf);
        cell_cycles.assign(cells, 0);
        cell_cycle_runs.assign(cells, 0);
        std::map<uint64_t, int64_t> hs_cycles;
        std::vector<int32_t> anchor_seq, anchor_hotspot;
        std::vector<int64_t> anchor_cycles;
        size_t path = 0;
        for (const auto &a : facts.fact_cycles) {
            if (a.ordinal >= total || a.cycles > uint64_t(INT64_MAX))
                fail(kExitConsistency, "Cycle anchor overflow");
            while (path + 1 < facts.fact_path_runs.size() &&
                   facts.fact_path_runs[path + 1].start <= a.ordinal)
                ++path;
            const auto cell = a.ordinal / 4096,
                       hs = uint64_t(st_hotspot[facts.fact_ids[a.ordinal]]);
            const auto leaf = facts.fact_path_runs[path].leaf;
            auto checked_add = [](int64_t &target, uint64_t value) {
                if (value > uint64_t(INT64_MAX - target))
                    fail(kExitConsistency, "Cycle sum overflow");
                target += value;
            };
            checked_add(cell_cycles[cell], a.cycles);
            ++cell_cycle_runs[cell];
            checked_add(dense_self_cycles[cell * node_count + leaf], a.cycles);
            checked_add(hs_cycles[cell * hotspot_count + hs], a.cycles);
            checked_add(hotspot_cycles[hs], a.cycles);
            anchor_seq.push_back(a.seq);
            anchor_hotspot.push_back(hs);
            anchor_cycles.push_back(a.cycles);
        }
        std::vector<int32_t> hs_cells, hs_hotspots;
        std::vector<int64_t> hs_values;
        for (const auto &p : hs_cycles) {
            hs_cells.push_back(p.first / hotspot_count);
            hs_hotspots.push_back(p.first % hotspot_count);
            hs_values.push_back(p.second);
        }
        add("hs_cycles_cells", 5, hs_cells);
        add("hs_cycles_hotspots", 5, hs_hotspots);
        add("hs_cycles_values", 7, hs_values);
        add("cycle_anchor_seq", 5, anchor_seq);
        add("cycle_anchor_hotspot", 5, anchor_hotspot);
        add("cycle_anchor_cycles", 7, anchor_cycles);
        add("cell_cycles", 7, cell_cycles);
        add("cell_cycle_runs", 7, cell_cycle_runs);
        std::vector<uint16_t> values(dense_self.size(), 0);
        std::vector<int64_t> cycles(dense_self.size(), 0);
        std::vector<int32_t> self_cells, self_nodes, self_counts;
        std::vector<int64_t> self_cycles;
        node_value.assign(node_count, 0);
        node_self.assign(node_count, 0);
        node_value_cycles.assign(node_count, 0);
        node_self_cycles.assign(node_count, 0);
        for (size_t c = 0; c < cells; ++c)
            for (size_t leaf = 0; leaf < node_count; ++leaf) {
                const size_t key = c * node_count + leaf;
                const auto count = dense_self[key];
                const auto cy = dense_self_cycles[key];
                if (!count && !cy)
                    continue;
                self_cells.push_back(c);
                self_nodes.push_back(leaf);
                self_counts.push_back(count);
                self_cycles.push_back(cy);
                node_self[leaf] += count;
                node_self_cycles[leaf] += cy;
                for (auto n : chains[leaf]) {
                    values[c * node_count + n] += count;
                    cycles[c * node_count + n] += cy;
                    node_value[n] += count;
                    node_value_cycles[n] += cy;
                }
            }
        add("node_self_cells", 5, self_cells);
        add("node_self_nodes", 5, self_nodes);
        add("node_self_counts", 5, self_counts);
        add("node_self_cycles", 7, self_cycles);
        add("cell_node_value", 2, values, node_count);
        add("cell_node_value_cycles", 7, cycles, node_count);
    }
    Json navigation() {
        std::vector<uint32_t> offsets{0}, pc_cells;
        for (const auto &values : facts.pc_cells_by_id) {
            if (values.size() > uint64_t(UINT32_MAX) - pc_cells.size())
                fail(kExitConsistency, "PC cell index overflow");
            pc_cells.insert(pc_cells.end(), values.begin(), values.end());
            offsets.push_back(pc_cells.size());
        }
        add("pc_cell_offsets", 4, offsets);
        add("pc_cells", 4, pc_cells);
        add("line_start", 4, facts.line_starts);
        add("line_id", 4, facts.line_ids);
        uLong crc = 0;
        for (const auto *v : {&offsets, &pc_cells, &facts.line_starts, &facts.line_ids})
            crc = crc32(crc, reinterpret_cast<const Bytef *>(v->data()),
                        v->size() * sizeof(uint32_t));
        return Json{{"cellSize", 4096},
                    {"staticCount", entries.size()},
                    {"instructions", total},
                    {"pcCellPairs", pc_cells.size()},
                    {"lineRuns", facts.line_starts.size()},
                    {"checksum", uint32_t(crc)}};
    }
    Json default_window() {
        const uint64_t step = (output.events + 1199) / 1200,
                       buckets = (output.events + step - 1) / step;
        Json timeline = Json::array();
        size_t event = 0, path = 0;
        for (uint64_t b = 0; b < buckets; ++b) {
            uint64_t lo = b * step, hi = std::min(output.events - 1, lo + step - 1),
                     begin = ordinal_before(lo), end = ordinal_before(hi + 1);
            Json events = Json::array();
            while (event < facts.fact_events.size() && facts.fact_events[event].seq <= hi) {
                const auto &e = facts.fact_events[event++];
                events.push_back(Json{
                    {"seq", e.seq}, {"type", e.type}, {"text", facts.fact_event_texts[e.text_id]}});
            }
            std::vector<std::string> prefix;
            bool present = false, mixed = false;
            if (begin < end) {
                while (path < facts.fact_path_runs.size() &&
                       facts.fact_path_runs[path].start + facts.fact_path_runs[path].count <= begin)
                    ++path;
                for (size_t p = path;
                     p < facts.fact_path_runs.size() && facts.fact_path_runs[p].start < end; ++p) {
                    const auto &value = paths[facts.fact_path_runs[p].leaf];
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
            uint64_t unknown = 0, not_taken = 0;
            // At most 1200 disjoint spans; every instruction is visited once.
            for (uint64_t i = begin; i < end; ++i) {
                unknown += facts.fact_states[i] == 2;
                not_taken += facts.fact_states[i] == 1;
            }
            if (mixed)
                prefix.push_back("多段调用（放大查看）");
            timeline.push_back(Json{{"startSeq", lo},
                                    {"endSeq", hi},
                                    {"firstSeq", lo},
                                    {"path", prefix},
                                    {"records", end - begin},
                                    {"unknown", unknown},
                                    {"notTaken", not_taken},
                                    {"mixed", mixed},
                                    {"events", events}});
        }
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
                         {"pc", st_pc[hotspot_first_id[hs]]}});
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
        return Json{{"range", range()},
                    {"firstSeq", output.first_instruction},
                    {"timing",
                     Json{{"axis", "execution-order"},
                          {"verifiedTime", false},
                          {"reason", "当前记录没有已验收的逐指令时间戳，执行序号不能换算为微秒"}}},
                    {"timeline", timeline},
                    {"resolution", step},
                    {"analysis", analysis}};
    }
    Json default_timeline() {
        const auto fs = functions.size();
        std::vector<int64_t> totals(fs, 0), unknown(1600, 0), not_taken(1600, 0);
        for (size_t b = 0; b < 1600; ++b)
            for (size_t fn = 0; fn < fs; ++fn) {
                size_t k = b * fs + fn;
                totals[fn] += timeline_counts[k] - timeline_unknown[k] - timeline_not_taken[k];
                unknown[b] += timeline_unknown[k];
                not_taken[b] += timeline_not_taken[k];
            }
        std::vector<size_t> order(fs);
        std::iota(order.begin(), order.end(), 0);
        std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
            return std::make_pair(-totals[a], functions[a]) <
                   std::make_pair(-totals[b], functions[b]);
        });
        std::vector<bool> top(fs, false);
        Json lanes = Json::array();
        for (size_t i = 0; i < std::min<size_t>(6, fs); ++i)
            if (totals[order[i]] > 0) {
                auto fn = order[i];
                top[fn] = true;
                std::vector<int64_t> bins(1600);
                for (size_t b = 0; b < 1600; ++b) {
                    size_t k = b * fs + fn;
                    bins[b] = timeline_counts[k] - timeline_unknown[k] - timeline_not_taken[k];
                }
                lanes.push_back(Json{{"key", "fn:" + functions[fn]},
                                     {"name", functions[fn]},
                                     {"kind", "function"},
                                     {"records", totals[fn]},
                                     {"bins", bins}});
            }
        auto add_lane = [&](const char *key, const char *name, const char *kind,
                            const std::vector<int64_t> &bins) {
            const auto sum = std::accumulate(bins.begin(), bins.end(), int64_t(0));
            if (sum)
                lanes.push_back(Json{{"key", key},
                                     {"name", name},
                                     {"kind", kind},
                                     {"records", sum},
                                     {"bins", bins}});
        };
        if (!lanes.empty()) {
            std::vector<int64_t> other(1600, 0);
            for (size_t b = 0; b < 1600; ++b)
                for (size_t fn = 0; fn < fs; ++fn)
                    if (!top[fn]) {
                        size_t k = b * fs + fn;
                        other[b] +=
                            timeline_counts[k] - timeline_unknown[k] - timeline_not_taken[k];
                    }
            add_lane("other", "其他函数", "other", other);
        }
        add_lane("unknown", "执行状态未知", "unknown", unknown);
        add_lane("not-taken", "未成立路径（未证实执行）", "not-taken", not_taken);
        Json markers = Json::array();
        uint64_t last = UINT64_MAX;
        for (const auto &ev : facts.fact_events) {
            uint64_t bin = std::min<uint64_t>(1599, ev.seq * 1600 / output.events);
            if (bin != last) {
                markers.push_back(Json{{"startSeq", ev.seq},
                                       {"endSeq", ev.seq},
                                       {"seq", ev.seq},
                                       {"types", Json::object()}});
                last = bin;
            }
            auto &marker = markers.back();
            marker["endSeq"] = ev.seq;
            const auto key = std::to_string(ev.type);
            marker["types"][key] = marker["types"].value(key, 0) + 1;
        }
        for (auto &m : markers) {
            int count = 0;
            for (const auto &v : m["types"])
                count += v.get<int>();
            m["count"] = count;
        }
        return Json{
            {"range", range()},
            {"lanes", lanes},
            {"binCount", 1600},
            {"markers", markers},
            {"markerCount", facts.fact_events.size()},
            {"summary",
             Json{{"executed", std::accumulate(totals.begin(), totals.end(), int64_t(0))},
                  {"unknown", std::accumulate(unknown.begin(), unknown.end(), int64_t(0))},
                  {"notTaken", std::accumulate(not_taken.begin(), not_taken.end(), int64_t(0))},
                  {"filteredRecords", output.events},
                  {"markers", facts.fact_events.size()}}},
            {"timing", Json{{"axis", "execution-order"},
                            {"verifiedTime", false},
                            {"reason", "当前记录没有已验收的逐指令时间戳，横轴只表示执行序号"}}}};
    }

  public:
    CompleteIndex(const StaticDict &d, const std::vector<const StaticEntry *> &e, ExecutionFacts &f,
                  const BuildOutput &o)
        : dict(d), entries(e), facts(f), output(o), total(f.fact_ids.size()),
          cells((total + 4095) / 4096), node_count(f.fact_path->nodes().size()), hotspot_count(0) {}
    CompleteIndexResult build() {
        if (!total || total > INT32_MAX || output.events > INT32_MAX || !node_count ||
            !facts.index_facts_enabled)
            fail(kExitConsistency, "Unsupported complete index input");
        const auto started = std::chrono::steady_clock::now();
        facts.finish(output.instructions);
        mappings();
        instruction_tables();
        path_cycle_tables();
        Json nav = navigation();
        CompleteIndexResult result;
        result.timings = Json{{"tablesSeconds", chrono_seconds(started)}};
        auto phase = std::chrono::steady_clock::now();
        Json defaults = Json::object();
        auto window = default_window();
        add_json("default_window_json", window, &defaults["window"], 1200);
        auto timeline = default_timeline();
        add_json("default_timeline_json", timeline, &defaults["timeline"], 1600);
        result.timings["defaultViewsSeconds"] = chrono_seconds(phase);
        std::vector<std::string> names;
        for (const auto &t : tables)
            names.push_back(t.name);
        std::sort(names.begin(), names.end());
        result.meta = Json{
            {"cellSize", 4096},
            {"instructions", total},
            {"events", facts.fact_events.size()},
            {"cells", cells},
            {"staticCount", entries.size()},
            {"functionCount", functions.size()},
            {"hotspotCount", hotspot_count},
            {"nodeCount", node_count},
            {"segmentCount", facts.fact_path_runs.size()},
            {"functionSegments", std::find_if(tables.begin(), tables.end(),
                                              [](const V2Table &t) { return t.name == "fs_start"; })
                                     ->shape0},
            {"firstSeq", 0},
            {"lastSeq", output.events - 1},
            {"strings", strings},
            {"functionNames", functions},
            {"format", "etm-trace-store-query-index"},
            {"version", 1},
            {"container", "v2"},
            {"source", "native-complete-index"},
            {"nav", nav},
            {"defaultViews", defaults},
            {"tables", names},
            {"coverage", Json::array({0, output.events - 1})},
            {"compatPending", Json::array()}};
        add_json("meta_json", result.meta);
        phase = std::chrono::steady_clock::now();
        result.payload = encode_v2_payload(tables, 1, 4);
        result.timings["encodeSeconds"] = chrono_seconds(phase);
        result.timings["totalSeconds"] = chrono_seconds(started);
        result.source_mapped = source_mapped;
        result.first_pc = st_pc[facts.fact_ids[0]];
        return result;
    }
};
