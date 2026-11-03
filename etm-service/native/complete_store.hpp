// Final JSON blocks are produced before the single store write. Only the
// bounded record metadata/context and final result cross the Python boundary.
#pragma once
std::string native_fault_name(uint32_t code, bool v3) {
    if (v3) {
        if (code == 2)
            return "INCOMPLETE_EOT.";
        if (code == 23)
            return "BAD_SEQUENCE";
        if (code == 24)
            return "BAD_TRACEMODE";
        return "I_RESERVED";
    }
    switch (code) {
    case 0x201:
        return "I_INCOMPLETE_EOT";
    case 0x300:
        return "I_BAD_SEQUENCE";
    case 0x301:
        return "I_BAD_TRACEMODE";
    case 0x302:
        return "I_RESERVED";
    case 0x303:
        return "I_RESERVED_CFG";
    case 0x105:
        return "I_OVERFLOW";
    default:
        return "I_UNKNOWN";
    }
}
Json read_context(const std::string &path) {
    std::error_code error;
    const auto size = fs::file_size(file_path(path), error);
    if (error || size > (64u << 20))
        fail(kExitInput, "Invalid or oversized complete-store context");
    std::ifstream input(file_path(path), std::ios::binary);
    if (!input)
        fail(kExitIo, "Cannot open complete-store context");
    Json value = Json::parse(input);
    if (!value.is_object() || value.value("format", std::string()) != "etm-complete-context/1")
        fail(kExitInput, "Invalid complete-store context version");
    return value;
}

Json finalize_complete_blocks(BuildOutput &out, const NativeCounters &c, ExecutionFacts &facts,
                              CompleteIndexResult &index, const Json &context,
                              const Json &analysis_value,
                              const std::map<uint16_t, uint64_t> &event_types) {
    const bool direct = context.at("direct").get<bool>();
    const auto &config = context.at("config");
    const auto &metadata = context.at("metadata");
    const auto &session = context.at("session");
    const auto &sources = context.at("sources");
    const uint64_t bytes = context.at("inputBytes").is_null()
                               ? c.status.processed
                               : context.at("inputBytes").get<uint64_t>();
    auto framing = context.value("framing", Json(nullptr));
    if (framing.is_null() && metadata.contains("framing"))
        framing = metadata["framing"];
    auto field = [&](const char *key, Json fallback = Json(nullptr)) {
        return framing.is_object() ? framing.value(key, fallback) : fallback;
    };
    auto truth = [](const Json &v) { return !v.is_null() && v != false && v != 0 && v != ""; };
    Json status{{"processed", c.status.processed},
                {"lastErrorCode", c.status.last_error_code},
                {"library", c.status.library},
                {"lastError", c.status.last_error},
                {"kind", "status"}};
    Json quality{
        {"inputBytes", bytes},
        {"unprocessedBytes", bytes > c.status.processed ? bytes - c.status.processed : 0},
        {"processedBytes", c.status.processed},
        {"accountedBytes", c.packet_covered},
        {"overlapBytes", c.packet_overlap},
        {"unaccountedBytes", bytes > c.packet_covered ? bytes - c.packet_covered : 0},
        {"unsynchronizedBytes", c.unsync_bytes},
        {"unsynchronizedRecords", c.packet_unsync},
        {"validPackets", c.saw_packets - c.packet_unsync - c.packet_invalid},
        {"packetIssues", c.packet_invalid},
        {"overflowPackets", c.packet_overflow},
        {"decoderLastError", c.status.last_error_code},
        {"unknownExecution", out.unknown},
        {"initialPhysicalBytes", field("initial_skipped_bytes")},
        {"unknownSourceBytes", field("unknown_bytes")},
        {"trailingFrameBytes", field("trailing_frame_bytes")},
        {"trailingSyncBytes", field("trailing_sync_bytes", 0)},
        {"firstPathOffset", c.first_range_offset},
        {"boundaryPresent", bool(c.unsync_bytes) || truth(field("initial_skipped_bytes")) ||
                                truth(field("trailing_frame_bytes")) ||
                                truth(field("trailing_sync_bytes", 0))},
        {"timing", Json{{"cycleElements", c.cycle_elements}, {"timeFlameAvailable", false}}},
        {"basis", "字节核算不等于采集无损证明；源码映射率不等于程序覆盖率"}};
    Json analysis = analysis_value;
    if (metadata.contains("analysis") && metadata["analysis"].contains("timing") &&
        metadata["analysis"]["timing"].contains("coreHz") &&
        !metadata["analysis"]["timing"]["coreHz"].is_null())
        analysis["timing"]["coreHz"] = metadata["analysis"]["timing"]["coreHz"];
    Json functions = Json::object();
    for (const auto &row : analysis["functions"])
        if (row["knownExecuted"] != 0)
            functions[row["function"].get<std::string>()] = row["knownExecuted"];
    Json summary{{"packets", out.packets},
                 {"ranges", out.ranges},
                 {"instructions", out.instructions},
                 {"executed", out.executed},
                 {"sourceMapped", index.source_mapped},
                 {"exceptions", out.exceptions},
                 {"gaps", out.gaps},
                 {"packetIssues", c.packet_invalid},
                 {"unknownExecution", out.unknown},
                 {"functions", functions}};
    Json counts{{"events", out.events},
                {"instructions", out.instructions},
                {"runs", out.runs},
                {"staticPcs", out.static_pcs},
                {"packets", out.packets}};
    Json decoded{{"version", 3},
                 {"protocol", config["protocol"]},
                 {"config", config},
                 {"inputBytes", bytes},
                 {"elf", Json{{"name", context.at("elfName")}, {"sha256", out.elf_sha256}}},
                 {"summary", summary},
                 {"quality", quality},
                 {"analysis", analysis},
                 {"status", status},
                 {"timeBasis", "execution order; no per-instruction timestamp"},
                 {"streamed", Json{{"eventsFile", "store.bin"},
                                   {"events", out.events},
                                   {"elements", c.saw_elements},
                                   {"packets", out.packets},
                                   {"nativeJsonl", direct ? Json(nullptr) : Json("native.bin")},
                                   {"schema", 2}}}};
    for (const auto *name : {"physical", "framing", "capture", "targetSnapshot", "captureScope",
                             "captureEntry", "captureStart", "laFilter", "spiValidation",
                             "samplingValidation", "phaseValidation", "recordError"})
        if (metadata.contains(name))
            decoded[name] = metadata[name];
    for (const auto *name : {"physical", "framing", "capture"})
        if (context.contains(name) && !context[name].is_null())
            decoded[name] = context[name];
    for (const auto *name : {"targetSnapshot", "captureScope", "laFilter"})
        if (!decoded.contains(name) && session.contains(name))
            decoded[name] = session[name];
    decoded["traceStore"] = Json{{"format", "trace-store v1"},
                                 {"schemaVersion", 1},
                                 {"store", "store"},
                                 {"source", direct ? "etm.bin" : "native.bin"},
                                 {"generation", out.generation},
                                 {"counts", counts}};
    Json reasons = Json::array({"IT 非分支条件指令：当前 trace 未记录条件结果"}),
         boundaries = Json::array(), extra = Json::array();
    std::map<std::string, uint32_t> reason_ids{{reasons[0].get<std::string>(), 0}};
    std::map<uint64_t, uint64_t> offsets;
    for (const auto &e : c.logical_events)
        offsets[e[0]] = e[1];
    for (const auto &e : facts.fact_events)
        if (is_boundary_type(e.type)) {
            const auto &reason = facts.fact_event_texts.at(e.text_id);
            auto item = reason_ids.emplace(reason, reasons.size());
            if (item.second)
                reasons.push_back(reason);
            boundaries.push_back(Json::array({e.seq, offsets.at(e.seq), item.first->second}));
        }
    // Fault names use the actual OpenCSD protocol, including legacy ETMv3.
    for (const auto &f : c.packet_faults) {
        auto name = native_fault_name(f[2], config.at("protocol") == "ETMv3");
        extra.push_back(Json{{"category", "packet"},
                             {"startSeq", nullptr},
                             {"endSeq", nullptr},
                             {"records", 0},
                             {"offset", f[0]},
                             {"bytes", f[1]},
                             {"reason", "包问题：" + name}});
    }
    if (bytes > c.packet_end)
        extra.push_back(Json{{"category", "gap"},
                             {"startSeq", nullptr},
                             {"endSeq", nullptr},
                             {"records", 0},
                             {"offset", c.packet_end},
                             {"bytes", bytes - c.packet_end},
                             {"reason", "ETM 输入尾部未被包记录覆盖"}});
    if (c.status.last_error_code)
        extra.push_back(
            Json{{"category", "decoder"},
                 {"startSeq", nullptr},
                 {"endSeq", nullptr},
                 {"records", 0},
                 {"offset", c.status.processed},
                 {"reason", "解码器错误：" + (c.status.last_error.empty() ? std::string("未知错误")
                                                                          : c.status.last_error)}});
    for (const auto &p : std::vector<std::pair<std::string, std::string>>{
             {"initialPhysicalBytes", "TPIU 同步前物理字节"},
             {"trailingFrameBytes", "不完整的 TPIU 尾帧"},
             {"unknownSourceBytes", "未知源 ID 字节"}})
        if (truth(quality[p.first]))
            extra.push_back(Json{{"category", "physical"},
                                 {"startSeq", nullptr},
                                 {"endSeq", nullptr},
                                 {"records", 0},
                                 {"bytes", quality[p.first]},
                                 {"reason", p.second}});
    const uint64_t issue_count = out.predicate_issues.size() + boundaries.size() + extra.size();
    std::string issue_text;
    if (context.value("compactIssues", true)) {
        // Write numeric runs directly; millions of boxed JSON values and their
        // copies would recreate the intermediate-object cost being removed.
        issue_text = "{\"format\": \"etm-issue-runs/1\", \"reasons\": " + python_json(reasons) +
                     ", \"predicates\": [";
        bool first = true;
        for (const auto &p : out.predicate_issues) {
            if (!first)
                issue_text += ", ";
            first = false;
            issue_text += '[';
            issue_text += std::to_string(p[0]) + ", " + std::to_string(p[1]) + ", " +
                          std::to_string(p[2]) + ']';
        }
        issue_text += "], \"boundaries\": " + python_json(boundaries) +
                      ", \"extra\": " + python_json(extra) +
                      ", \"total\": " + std::to_string(issue_count) + '}';
    } else {
        Json rows = Json::array();
        for (const auto &b : boundaries)
            rows.push_back(Json{{"category", "boundary"},
                                {"startSeq", b[0]},
                                {"endSeq", b[0]},
                                {"records", 1},
                                {"offset", b[1]},
                                {"reason", reasons[b[2].get<size_t>()]}});
        for (const auto &p : out.predicate_issues)
            rows.push_back(Json{{"category", "predicate"},
                                {"startSeq", p[0]},
                                {"endSeq", p[1]},
                                {"records", p[1] - p[0] + 1},
                                {"offset", p[2]},
                                {"reason", reasons[0]}});
        std::stable_sort(rows.begin(), rows.end(), [](const Json &a, const Json &b) {
            return a["startSeq"].get<uint64_t>() < b["startSeq"].get<uint64_t>();
        });
        for (auto &e : extra)
            rows.push_back(e);
        issue_text = python_json(rows);
    }
    Json index_meta = Json::object();
    for (const auto *key :
         {"format", "version", "cellSize", "instructions", "events", "cells", "staticCount",
          "functionCount", "hotspotCount", "nodeCount", "segmentCount", "functionSegments",
          "firstSeq", "lastSeq", "nav", "container", "tables", "coverage", "defaultViews"})
        index_meta[key] = index.meta.at(key);
    index_meta["payloadBytes"] = index.payload.size();
    index_meta["buildSeconds"] = index.timings["totalSeconds"];
    index_meta["defaultsSeconds"] = index.timings["defaultViewsSeconds"];
    index_meta["builtAtUnix"] = std::time(nullptr);
    index_meta["builtBy"] = "native-complete-index";
    Json meta = Json::parse(meta_json(out, event_types));
    meta["record"]["protocol"] = config.at("protocol");
    meta["queryIndex"] = index_meta;
    meta["issues"] = issue_count;
    meta["verify"] = Json{{"elements", true},
                          {"elementsVerified", out.ranges},
                          {"image", true},
                          {"machineCodeCrossCheck", true},
                          {"staticPcs", out.static_pcs}};
    meta["packetText"] = Json{{"available", false}, {"reason", "按需重放原始 ETM 生成包说明"}};
    if (direct)
        meta["record"]["eventsSource"] = "etm.bin";
    meta["captureStartIndex"] = Json{{"version", 1},
                                     {"firstRecoveredSeq", out.first_instruction},
                                     {"firstRecoveredPC", index.first_pc},
                                     {"staticPcsAreRecovered", true}};
    Json stored = decoded;
    stored["eventCount"] = out.events;
    stored["packetCount"] = out.packets;
    std::vector<std::string> files;
    for (auto it = sources.begin(); it != sources.end(); ++it)
        files.push_back(it.key());
    stored["sourceFiles"] = files;
    stored["firstSeq"] = out.first_instruction;
    out.blocks.erase(std::remove_if(out.blocks.begin(), out.blocks.end(),
                                    [](const BuildBlock &b) {
                                        return (b.type >= 7 && b.type <= 10) || b.type == 12;
                                    }),
                     out.blocks.end());
    add_json_block(out, 7, python_json(meta));
    add_json_block(out, 8, python_json(stored));
    add_json_block(out, 9, python_json(sources));
    add_json_block(out, 10, issue_text);
    BuildBlock block;
    block.type = 12;
    block.count = static_cast<uint32_t>(index.meta.at("cells").get<uint64_t>());
    block.payload = std::move(index.payload);
    out.blocks.push_back(std::move(block));
    out.required_features = context.value("compactIssues", true) ? 2 : 0;
    out.optional_features = 1;
    return Json{{"decoded", decoded},
                {"meta", meta},
                {"queryIndex", index_meta},
                {"indexTimings", index.timings}};
}
