"""Evidence-preserving Huangshan route baseline. Python 3.10+, standard library."""

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import re

from entity_source import EntityIndex

ROOT = Path(__file__).resolve().parents[3]
MODULE = Path(__file__).resolve().parents[1]
PERIODS = ("morning", "noon", "afternoon", "evening", "unknown")
LABELS = dict(zip(PERIODS, ("上午", "中午", "下午", "傍晚及夜间", "时间未知")))
ARROW = re.compile(r"(?:->|→|——|—>|⇒)")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def spans(text):
    """Yield sentence/line spans in original Python character coordinates."""
    for match in re.finditer(r"[^。！？\n]+[。！？]?", text):
        start, end = match.span()
        while start < end and text[start].isspace():
            start += 1
        if start < end:
            yield start, end


def split_top_level(text):
    """Split route arrows outside parentheses; keep original offsets."""
    depth, start, result = 0, 0, []
    i = 0
    while i < len(text):
        char = text[i]
        if char in "（(":
            depth += 1
        elif char in "）)":
            depth = max(0, depth - 1)
        match = ARROW.match(text, i) if not depth else None
        if match:
            result.append((start, i))
            start = match.end()
            i = start
        else:
            i += 1
    result.append((start, len(text)))
    return result


def parenthetical_spans(text):
    return [m.span() for m in re.finditer(r"（[^（）]*）|\([^()]*\)", text)]


class Extractor:
    def __init__(self, config, entity_index=None):
        self.config = config
        self.entity_index = entity_index
        self.names = {}
        for poi in config["pois"]:
            for name in [poi["name"], *poi.get("aliases", [])]:
                if name in self.names:
                    raise ValueError(f"Duplicate alias: {name}")
                self.names[name] = poi
        self.pattern = re.compile("|".join(re.escape(s) for s in sorted(self.names, key=len, reverse=True)))

    def mentions(self, text, offset=0, record=None):
        if self.entity_index is not None and record is not None:
            return self.entity_index.mentions(record, offset, offset + len(text))
        return [{"name": self.names[m.group()]["name"], "surface": m.group(),
                 "entity_type": self.names[m.group()]["type"],
                 "start": offset + m.start(), "end": offset + m.end()}
                for m in self.pattern.finditer(text)]

    @staticmethod
    def evidence(record, start, end):
        return {"doc_id": record["doc_id"], "start": start, "end": end,
                "text": record["clean_text"][start:end]}

    def step(self, record, mention, start, end, day, status, rule):
        evidence = self.evidence(record, start, end)
        # Exact spans only: no guessed clock time, duration or implicit time propagation.
        period, time_text = "unknown", None
        phrase = evidence["text"]
        for pattern, value in ((r"上午|早上|清晨", "morning"), (r"中午|午间", "noon"),
                               (r"下午", "afternoon"), (r"日落后|傍晚|晚上|当晚|日落", "evening")):
            found = re.search(pattern, phrase)
            if found:
                period, time_text = value, found.group()
                break
        # Scope explicit time to the local activity, not a future hotel stay mentioned elsewhere.
        if time_text == "当晚" and mention and mention["entity_type"] != "hotel":
            period, time_text = "unknown", None
        item = {"poi": mention["name"] if mention else None,
                "activity_label": mention["name"] if mention else {
                    "explicit_unnamed_transport": "乘面包车前往车站",
                    "transport_choice": "上山索道二选一",
                    "unresolved_transport_activity": "索道上山（线路未消解）",
                    "explicit_trip_end": "行程结束"
                }.get(rule, "未命名活动"),
                "surface": mention["surface"] if mention else None,
                "entity_type": mention["entity_type"] if mention else "activity",
                "mention_span": ({"start": mention["start"], "end": mention["end"]} if mention else None),
                "activity": phrase, "day": day, "time": None, "duration_minutes": None,
                "time_period": period, "time_expression": time_text,
                "time_basis": "explicit_same_sentence" if time_text else "unknown",
                "inferred": False, "visit_status": status, "extraction_rule": rule,
                "evidence": evidence}
        if self.entity_index is not None:
            entities = self.entity_index.between(record, start, end)
            item["source_entity_id"] = mention.get("source_entity_id") if mention else None
            item["context_entity_ids"] = [e["entity_id"] for e in entities]
            item["transport_entity_ids"] = [e["entity_id"] for e in entities if e["entity_type"] == "TRANSPORT"]
            item["time_entity_ids"] = [e["entity_id"] for e in entities if e["entity_type"] == "TIME"]
            item.update(self.entity_index.time_for_step(record, start, end, mention))
        return item

    def official(self, record):
        text = record["clean_text"]
        route = self.route(record, "official_recommended")
        numbered = list(re.finditer(r"(?m)^\s*\d+[.、．]\s*(.+)$", text))
        route["format"] = "numbered" if len(numbered) >= 2 else "arrow_narrative"
        chunks = [(m.start(1), m.end(1)) for m in numbered] if numbered else split_top_level(text)
        for start, end in chunks:
            chunk = text[start:end]
            parens = parenthetical_spans(chunk)
            local = self.mentions(chunk, start, record)
            main = [m for m in local if not any(a <= m["start"] - start < b for a, b in parens)]
            # First official clause offers alternative cable cars; do not turn OR into NEXT.
            alternatives = []
            if "或" in chunk:
                for left, right in zip(main, main[1:]):
                    if "或" in text[left["end"]:right["start"]]:
                        alternatives.extend([left, right])
            alternative_names = {m["name"] for m in alternatives}
            if alternatives:
                choice = self.step(record, None, start, end, 1, "recommended", "transport_choice")
                choice["choices"] = list(dict.fromkeys(m["name"] for m in alternatives))
                choice["choice_mentions"] = alternatives
                choice["choice_semantics"] = "choose_one"
                route["steps"].append(choice)
            for mention in main:
                if mention["name"] in alternative_names:
                    continue
                route["steps"].append(self.step(record, mention, start, end, 1, "recommended", route["format"]))
            for a, b in parens:
                part = chunk[a:b]
                mentions = self.mentions(part, start + a, record)
                if not mentions:
                    continue
                if re.search(r"远观|远眺", part):
                    for mention in mentions:
                        route["non_main_mentions"].append(self.step(record, mention, start+a, start+b, 1, "remote_view", "remote_parenthesis"))
                elif re.search(r"如|若|如果", part):
                    anchor = main[-1]["name"] if main else None
                    condition = re.search(r"(?:如果|如|若)[^，,）)]*", part)
                    branch = {"anchor_poi": anchor, "condition": condition.group() if condition else part,
                              "evidence": self.evidence(record, start+a, start+b), "steps": []}
                    for mention in mentions:
                        item = self.step(record, mention, start+a, start+b, 1, "optional", "conditional_parenthesis")
                        item["return_to_anchor"] = bool("返回" in part and mention["name"] == anchor)
                        branch["steps"].append(item)
                    route["optional_branches"].append(branch)
        return self.finalize(route)

    @staticmethod
    def route(record, kind):
        return {"route_id": record["doc_id"] + ":" + kind, "doc_id": record["doc_id"],
                "scenic_id": record["scenic_id"], "scenic_name": record["scenic_name"],
                "source_url": record["source_url"], "text_type": record["text_type"],
                "route_kind": kind, "steps": [], "optional_branches": [], "non_main_mentions": [],
                "excluded_steps": [], "warnings": []}

    def day_at(self, text, start, record=None):
        # T+1 is a relative day marker, not a calendar date.
        if self.entity_index is not None and record is not None:
            return self.entity_index.day_at(record, start)
        markers = list(re.finditer(r"(?m)^T\s*\+\s*(\d+)", text[:start]))
        return int(markers[-1].group(1)) + 1 if markers else 1

    def classify(self, sentence, mention, sentence_start, record=None):
        if mention["entity_type"] == "peripheral":
            return "peripheral", "peripheral_dictionary"
        if self.entity_index is not None and record is not None and mention.get("upstream_entity_type") == "POI":
            following = record["clean_text"][mention["end"]:mention["end"]+2]
            if following in {"索道", "缆车"}:
                return "boundary_ambiguous", "place_transport_composite"
        relative_start, relative_end = mention["start"] - sentence_start, mention["end"] - sentence_start
        boundaries = [m.start() for m in re.finditer(r"[，,；;（）()]", sentence)]
        left = max([b + 1 for b in boundaries if b < relative_start], default=0)
        right = min([b for b in boundaries if b >= relative_end], default=len(sentence))
        clause = sentence[left:right]
        after, before = sentence[relative_end:right], sentence[left:relative_start]
        # Deferred negation can span clauses, but only propagate with a single named target.
        negation_context = sentence if len(self.mentions(sentence, sentence_start, record)) == 1 else clause
        if re.search(r"未能前往|没有(?:去|前往)|未(?:到访|去过)|没去", negation_context):
            return "not_visited", "explicit_negation"
        if re.search(r"下次|或许|要是|本来打算|原计划", clause):
            return "hypothetical", "future_or_counterfactual"
        if re.search(r"仿佛|可能|一般可以|听.*说|可以看到|可以想象|从其他人", clause):
            return "mentioned", "description_or_hearsay"
        if "游客" in clause and not re.search(r"过了|走到|到达", before):
            return "mentioned", "other_travellers"
        if re.match(r"前", after) and re.search(r"到达$", before):
            return "approach", "before_arrival"
        if re.search(r"往.*方向|去往", clause) and not re.search(r"到了|到达了|走到|入住", clause):
            return "approach", "direction_not_arrival"
        if "从" in before and re.match(r"(?:走到|过来|出来|往下走|下来|下山)", after):
            return "confirmed", "departure_reference"
        if re.search(r"穿过|走到|到达|到了|出来|下来|下山|过了|爬.*之后|爬.*路上|坐.*索道|索道上山|从.*往下走", clause):
            return "confirmed", "explicit_movement"
        return "mentioned", "no_visit_evidence"

    def tourist(self, record):
        text = record["clean_text"]
        observed = self.route(record, "tourist_observed")
        declared = self.route(record, "tourist_declared")
        declared["format"] = "arrow_list"
        observed["format"] = "narrative_rules"
        sentences = list(spans(text))
        negative = {}
        confirmed = {}
        for start, end in sentences:
            sentence = text[start:end]
            if len(ARROW.findall(sentence)) >= 2:
                continue
            day = self.day_at(text, start, record)
            mentions = self.mentions(sentence, start, record)
            if not mentions and re.search(r"早上.*面包车.*前往车站", sentence):
                observed["steps"].append(self.step(record, None, start, end, day, "confirmed", "explicit_unnamed_transport"))
            if (not mentions and self.entity_index is not None
                    and any(e["entity_type"] == "TIME" and e["subtype"] == "clock" for e in self.entity_index.between(record, start, end))
                    and re.search(r"终于.*(?:带回|到家|回到)", sentence)):
                observed["steps"].append(self.step(record, None, start, end, day, "confirmed", "explicit_trip_end"))
            if (self.entity_index is not None and "便是索道上山" in sentence
                    and any(self.classify(sentence, m, start, record)[0] == "boundary_ambiguous" for m in mentions)):
                observed["steps"].append(self.step(record, None, start, end, day, "confirmed", "unresolved_transport_activity"))
            for mention in mentions:
                status, rule = self.classify(sentence, mention, start, record)
                item = self.step(record, mention, start, end, day, status, rule)
                if status == "confirmed":
                    if rule == "departure_reference" and (day, mention["name"]) in confirmed:
                        observed["non_main_mentions"].append({**item, "visit_status": "retrospective_reference"})
                        continue
                    confirmed.setdefault((day, mention["name"]), []).append(item["evidence"])
                    # Collapse only adjacent same-day repeats; preserve returns after other stops.
                    if not observed["steps"] or (observed["steps"][-1]["poi"], observed["steps"][-1]["day"]) != (item["poi"], day):
                        observed["steps"].append(item)
                    else:
                        observed["steps"][-1].setdefault("additional_evidence", []).append(item["evidence"])
                else:
                    observed["non_main_mentions"].append(item)
                    if status == "not_visited":
                        negative[(day, mention["name"])] = item["evidence"]
        for start, end in sentences:
            sentence = text[start:end]
            if len(ARROW.findall(sentence)) < 2:
                continue
            day = self.day_at(text, start, record)
            for mention in self.mentions(sentence, start, record):
                key = day, mention["name"]
                item = self.step(record, mention, start, end, day, "reported", "tourist_arrow_list")
                if key in negative:
                    item["visit_status"] = "not_visited"
                    item["contradiction_evidence"] = negative[key]
                    declared["excluded_steps"].append(item)
                else:
                    if key in confirmed:
                        item["visit_status"] = "corroborated"
                        item["corroborating_evidence"] = confirmed[key]
                    declared["steps"].append(item)
        observed["warnings"].append("叙述事件是保守规则候选；同句实体间的微观先后未经人工标注验收，不能视作完整真实轨迹。")
        declared["warnings"].append("列表中未被否定的节点仅为作者报告路线；未被叙述证实不等于已到访。删除否定节点不证明其前后节点之间有直接通路。")
        return self.finalize(observed), self.finalize(declared)

    @staticmethod
    def finalize(route):
        days = {}
        for index, item in enumerate(route["steps"], 1):
            item["step_id"] = route["route_id"] + f":s{index:03d}"
            item["order"] = index
            groups = days.setdefault(item["day"], {period: [] for period in PERIODS})
            groups[item["time_period"]].append(item["step_id"])
        route["time_hierarchy"] = [{"day": day, "periods": groups} for day, groups in sorted(days.items())]
        for number, branch in enumerate(route["optional_branches"], 1):
            branch["branch_id"] = route["route_id"] + f":b{number:03d}"
            branch["anchor_step_id"] = next((s["step_id"] for s in route["steps"] if s["poi"] == branch["anchor_poi"]), None)
            for index, item in enumerate(branch["steps"], 1):
                item["step_id"] = branch["branch_id"] + f":s{index:03d}"
                item["order"] = index
        route["warnings"].append("time和duration_minutes为空表示来源未提供；时间层级保留unknown，不按步骤均分上午/下午。")
        return route


def lcs_length(left, right):
    row = [0] * (len(right) + 1)
    for value in left:
        previous, row[0] = row[0], 0
        for j, other in enumerate(right, 1):
            old = row[j]
            row[j] = previous + 1 if value == other else max(row[j], row[j-1])
            previous = old
    return row[-1]


def compare(official, tourist):
    # Compare exact normalized non-transport POIs; preserve repeat visits for sequence metrics.
    def sequence(route):
        return [s["poi"] for s in route["steps"] if s["poi"] and s["entity_type"] not in {"transport", "peripheral"}]
    left, right = sequence(official), sequence(tourist)
    a, b = set(left), set(right)
    common = a & b
    projected_left, projected_right = [x for x in left if x in common], [x for x in right if x in common]
    common_lcs = lcs_length(projected_left, projected_right)
    return {"official_route_id": official["route_id"], "tourist_route_id": tourist["route_id"],
            "official_sequence": left, "tourist_sequence": right, "shared_pois": sorted(common),
            "official_only": sorted(a-b), "tourist_only": sorted(b-a),
            "official_poi_coverage": len(common)/len(a) if a else None,
            "poi_jaccard": len(common)/len(a|b) if a|b else None,
            "lcs_length": lcs_length(left, right),
            "lcs_dice": 2*lcs_length(left, right)/(len(left)+len(right)) if left or right else None,
            "shared_order_lcs_dice": 2*common_lcs/(len(projected_left)+len(projected_right)) if len(common) >= 2 else None,
            "shared_order_note": "共同景点少于2个时不报告顺序一致性；重复到访保留。",
            "interpretation": "样本描述性对比，非抽取准确率；官方一日路线与游客两天叙述范围不同，低相似度不能直接解释为游客偏离。"}


def validate_evidence(value, records):
    if isinstance(value, dict):
        if {"doc_id", "start", "end", "text"} <= value.keys():
            text = records[value["doc_id"]]["clean_text"]
            if not (0 <= value["start"] < value["end"] <= len(text)) or text[value["start"]:value["end"]] != value["text"]:
                raise ValueError(f"Evidence mismatch: {value}")
        if value.get("mention_span"):
            span = value["mention_span"]
            text = records[value["evidence"]["doc_id"]]["clean_text"]
            if text[span["start"]:span["end"]] != value["surface"]:
                raise ValueError("Mention offset mismatch")
        for child in value.values():
            validate_evidence(child, records)
    elif isinstance(value, list):
        for child in value:
            validate_evidence(child, records)


def render_html(routes):
    esc = html.escape
    titles = {"official_recommended": "官方推荐路线", "tourist_observed": "游客叙述中的游览事件", "tourist_declared": "游客报告路线（剔除否定节点后）"}
    statuses = {"recommended": "官方推荐", "confirmed": "有明确叙述线索", "reported": "仅在路线列表报告", "corroborated": "列表与叙述相互支持"}
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>黄山路线层级</title>',
             '<style>body{font:16px/1.7 "Microsoft YaHei",sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#18232d}h1,h2,h3{line-height:1.4}li{margin:12px 0}small{color:#52616d}details{margin:8px 0}section{margin:40px 0;border-top:1px solid #ddd}a{color:#235b88}</style>',
             '<h1>黄山路线层级与证据</h1><p>仅处理黄山官方路线与游客游记两条开发文本。展开每步可核对原文。</p><p>时段组用于归类，不构成跨组时序；整体顺序以步骤编号为准。缺失时刻保留未知，列表顺序不证明实际道路连通。</p>']
    for route in routes:
        parts.append('<section><h2>'+esc(titles[route['route_kind']])+' · '+esc(route['doc_id'])+'</h2>')
        by_id = {s['step_id']: s for s in route['steps']}
        for day in route['time_hierarchy']:
            parts.append(f'<h3>第{day["day"]}天</h3>')
            for period, ids in day['periods'].items():
                if not ids:
                    continue
                parts.append('<h4>'+LABELS[period]+'</h4><ul>')
                for step_id in ids:
                    s = by_id[step_id]
                    name = s['poi'] or ' / '.join(s.get('choices', [])) or s['activity_label']
                    e = s['evidence']
                    info = statuses[s['visit_status']] + (' · '+s['time'] if s['time'] else '')
                    parts.append('<li>'+esc('步骤 '+str(s['order'])+'：'+name)+' <small>'+esc(info)+'</small><details><summary>原文证据</summary>'+esc(e['text'])+f'<p>Python字符位置 [{e["start"]}, {e["end"]})</p></details></li>')
                parts.append('</ul>')
        if route['optional_branches']:
            parts.append('<h3>可选支线</h3><ul>')
            for b in route['optional_branches']:
                names = ' → '.join(s['poi'] for s in b['steps'])
                parts.append('<li>'+esc(str(b['anchor_poi'])+'：'+b['condition']+'；'+names)+'</li>')
            parts.append('</ul>')
        if route['excluded_steps']:
            parts.append('<h3>被后文否定的列表节点</h3><ul>')
            for s in route['excluded_steps']:
                parts.append('<li>'+esc(s['poi']+'：'+s['contradiction_evidence']['text'])+'</li>')
            parts.append('</ul>')
        parts.extend('<p><small>'+esc(w)+'</small></p>' for w in route['warnings'])
        parts.append('</section>')
    return '\n'.join(parts) + '</html>\n'


def run(input_path, output_dir, scenic_id="huangshan", config_path=None, entities_path=None, entity_mode="exp02"):
    config_path = config_path or MODULE / "config/huangshan_pois.json"
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if scenic_id != config["scenic_id"]:
        raise ValueError("配置景区与--scenic-id不一致；其他景区需提供独立词表，不能宣称已支持。")
    source_bytes = Path(input_path).read_bytes()
    records = json.loads(source_bytes.decode("utf-8-sig"))
    records = [r for r in records if r["scenic_id"] == scenic_id]
    if not records or len({r["doc_id"] for r in records}) != len(records):
        raise ValueError("景区数据为空或doc_id重复")
    if not {"official_route", "tourist_note"} <= {r["text_type"] for r in records}:
        raise ValueError("至少需要一条官方路线和一篇游客游记")
    if entity_mode not in {"exp02", "dictionary"}:
        raise ValueError("entity_mode必须为exp02或dictionary")
    entities_path = Path(entities_path or ROOT / "experiments/exp02_entity_recognition/outputs/entities_v2.json")
    entity_index = EntityIndex(entities_path, {r["doc_id"]: r for r in records}) if entity_mode == "exp02" else None
    extractor, routes = Extractor(config, entity_index), []
    for record in sorted(records, key=lambda r: r["doc_id"]):
        if record["text_type"] == "official_route":
            routes.append(extractor.official(record))
        elif record["text_type"] == "tourist_note":
            routes.extend(extractor.tourist(record))
    result = {"schema_version": "1.1", "scenic_id": scenic_id,
              "input_sha256": hashlib.sha256(source_bytes).hexdigest(),
              "config_sha256": hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
              "input_doc_ids": [r["doc_id"] for r in records],
              "clean_text_sha256": {r["doc_id"]: hashlib.sha256(r["clean_text"].encode("utf-8")).hexdigest() for r in records},
              "entity_source": "exp02_entities_v2" if entity_index else "local_development_dictionary",
              "exp02_integration_status": "integrated_position_validated" if entity_index else "dictionary_baseline_only",
              "scope": "黄山两条开发文本的规则基线，尚无独立人工金标准；不报告抽取准确率。",
              "routes": routes}
    if entity_index:
        result["upstream_entities"] = entity_index.metadata
        result["source_entities"] = entity_index.entities
        for route in routes:
            route["temporal_context"] = entity_index.temporal_context(next(r for r in records if r["doc_id"] == route["doc_id"]))
    validate_evidence(result, {r["doc_id"]: r for r in records})
    comparisons = [compare(a, b) for a in routes if a["route_kind"] == "official_recommended"
                   for b in routes if b["route_kind"] in {"tourist_observed", "tourist_declared"}]
    output_dir = Path(output_dir)
    write_json(output_dir / "routes_huangshan.json", result)
    write_json(output_dir / "comparison.json", {"comparisons": comparisons,
        "metrics": {"official_poi_coverage": "|official∩tourist|/|official|（集合）",
                    "poi_jaccard": "|official∩tourist|/|official∪tourist|（集合）",
                    "lcs_dice": "2*LCS(official,tourist)/(len(official)+len(tourist))（序列）",
                    "shared_order_lcs_dice": "仅保留共同景点后的LCS Dice；共同景点至少2个"}})
    review = [{"route_id": r["route_id"], "category": field, "item": item}
              for r in routes for field in ("optional_branches", "non_main_mentions", "excluded_steps") for item in r[field]]
    write_json(output_dir / "review_cases.json", {"note": "规则诊断待核验清单，不是人工标注或准确率。", "cases": review})
    with (output_dir / "route_steps.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["route_id", "doc_id", "order", "day", "poi", "surface", "entity_type", "visit_status", "time_period", "time", "activity_label", "activity", "source_entity_id", "start", "end"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for route in routes:
            for step in route["steps"]:
                writer.writerow({**{k: step.get(k) for k in fields if k not in {"route_id", "doc_id", "start", "end"}},
                                 "route_id": route["route_id"], "doc_id": route["doc_id"],
                                 "start": step["evidence"]["start"], "end": step["evidence"]["end"]})
    (output_dir / "hierarchy.html").write_text(render_html(routes), encoding="utf-8", newline="\n")
    summary = {"input_doc_ids": result["input_doc_ids"], "route_count": len(routes),
               "steps_by_route": {r["route_kind"]: len(r["steps"]) for r in routes},
               "optional_branches": sum(len(r["optional_branches"]) for r in routes),
               "excluded_list_steps": sum(len(r["excluded_steps"]) for r in routes),
               "evidence_validation": "passed", "evaluation": "development_diagnostics_only"}
    if entity_index:
        summary["upstream_entity_mentions"] = len(entity_index.entities)
        summary["entity_source"] = result["entity_source"]
    write_json(output_dir / "summary.json", summary)
    write_json(output_dir / "integration_report.json", {"entity_mode": entity_mode,
        "upstream": entity_index.metadata if entity_index else None,
        "semantic_evaluation": "尚无路线级独立人工金标准，位置校验通过不等于语义准确。",
        "known_upstream_issues": ["小火车仅识别出火车的边界问题保留在来源实体中；不补造乘坐小火车的活动。",
                                  "云谷寺索道在上游拆成云谷寺与泛称索道；本模块不自动归并为云谷索道。"] if entity_index else []})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/processed/sample_v1.json")
    parser.add_argument("--output-dir", type=Path, default=MODULE / "outputs")
    parser.add_argument("--scenic-id", default="huangshan")
    parser.add_argument("--config", type=Path, default=MODULE / "config/huangshan_pois.json")
    parser.add_argument("--entities", type=Path, default=ROOT / "experiments/exp02_entity_recognition/outputs/entities_v2.json")
    parser.add_argument("--entity-mode", choices=("exp02", "dictionary"), default="exp02")
    args = parser.parse_args()
    run(args.input, args.output_dir, args.scenic_id, args.config, args.entities, args.entity_mode)
