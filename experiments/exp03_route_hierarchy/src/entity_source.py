"""Read project 2 mentions without rerunning NER or collapsing category identities."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def clause_span(text, start, end, mention=None):
    if not mention:
        return start, end
    cuts = [m.start() for m in re.finditer(r"[，,；;（）()]", text[start:end])]
    left = max((start + p + 1 for p in cuts if start + p < mention["start"]), default=start)
    right = min((start + p for p in cuts if start + p >= mention["end"]), default=end)
    return left, right


class EntityIndex:
    def __init__(self, path, records):
        self.path = Path(path)
        source = self.path.read_bytes()
        raw = json.loads(source.decode("utf-8-sig"))
        if not isinstance(raw, list):
            raise ValueError("项目2实体输入必须是JSON数组")
        self.by_doc = {doc: [] for doc in records}
        self.entities = []
        seen = set()
        for entity in raw:
            required = {"doc_id", "scenic_id", "text", "entity_type", "start", "end", "subtype", "granularity", "canonical"}
            if not isinstance(entity, dict) or not required <= entity.keys():
                raise ValueError("项目2实体缺少接口字段")
            doc_id = entity["doc_id"]
            if doc_id not in records:
                raise ValueError(f"项目2实体引用了当前景区输入以外的doc_id: {doc_id}")
            record = records[doc_id]
            a, b = entity["start"], entity["end"]
            if type(a) is not int or type(b) is not int or not (0 <= a < b <= len(record["clean_text"])):
                raise ValueError(f"项目2实体位置非法: {doc_id} {a}:{b}")
            if record["clean_text"][a:b] != entity["text"]:
                raise ValueError(f"项目2实体与clean_text不一致: {doc_id} {a}:{b}")
            if entity["scenic_id"] != record["scenic_id"] or entity["entity_type"] not in {"POI", "TRANSPORT", "TIME"}:
                raise ValueError("项目2实体景区或类型不一致")
            identity = (doc_id, a, b)
            if identity in seen:
                raise ValueError(f"项目2实体位置重复: {identity}")
            seen.add(identity)
            item = {**entity, "entity_id": f'{doc_id}:{entity["entity_type"]}:{a}:{b}'}
            self.entities.append(item)
            self.by_doc[doc_id].append(item)
        if any(not entities for entities in self.by_doc.values()):
            raise ValueError("项目2实体没有覆盖当前景区的每条输入文本")
        for entities in self.by_doc.values():
            entities.sort(key=lambda e: (e["start"], e["end"]))
            if any(a["end"] > b["start"] for a, b in zip(entities, entities[1:])):
                raise ValueError("项目2实体出现重叠，需核对上游版本")
        self.entities.sort(key=lambda e: (e["doc_id"], e["start"], e["end"]))
        self.metadata = {"artifact_name": self.path.name, "sha256": hashlib.sha256(source).hexdigest(),
                         "entity_mentions": len(self.entities),
                         "by_type": dict(sorted(Counter(e["entity_type"] for e in self.entities).items())),
                         "per_doc": {doc: len(es) for doc, es in sorted(self.by_doc.items())},
                         "position_validation": "passed",
                         "identity_policy": "doc_id:type:start:end；名称使用text去空白，canonical仅保留为类别属性"}

    def between(self, record, start, end):
        return [e for e in self.by_doc[record["doc_id"]] if start <= e["start"] and e["end"] <= end]

    def mentions(self, record, start, end):
        result = []
        for entity in self.between(record, start, end):
            kind = entity["entity_type"]
            if kind == "TIME" or (kind == "TRANSPORT" and entity["granularity"] != "specific"):
                continue
            node_type = "transport" if kind == "TRANSPORT" else {
                "lodging": "hotel", "area": "region", "gate": "place",
                "restaurant": "restaurant", "town": "peripheral", "resort": "peripheral"
            }.get(entity["subtype"], "poi")
            result.append({"name": re.sub(r"\s+", "", entity["text"]), "surface": entity["text"],
                           "entity_type": node_type, "start": entity["start"], "end": entity["end"],
                           "source_entity_id": entity["entity_id"], "upstream_entity_type": kind,
                           "upstream_subtype": entity["subtype"], "granularity": entity["granularity"]})
        return result

    def day_at(self, record, position):
        day = 1
        for entity in self.by_doc[record["doc_id"]]:
            if entity["end"] > position or entity["entity_type"] != "TIME" or entity["subtype"] != "day":
                continue
            relative = re.fullmatch(r"T\s*\+\s*(\d+)", entity["text"])
            if relative:
                day = int(relative.group(1)) + 1
            elif entity["text"] == "第二天":
                day = 2
        return day

    @staticmethod
    def period(entity):
        word = entity["text"]
        if entity["subtype"] == "clock":
            clock = re.fullmatch(r"(\d{2}):?(\d{2})", word)
            if clock and int(clock.group(1)) < 24 and int(clock.group(2)) < 60:
                hour = int(clock.group(1))
                return "morning" if hour < 11 else "noon" if hour < 14 else "afternoon" if hour < 18 else "evening"
            return "unknown"
        if entity["subtype"] not in {"period", "event"}:
            return "unknown"
        if re.search(r"上午|早上|清晨|日出", word):
            return "morning"
        if re.search(r"中午|午间", word):
            return "noon"
        if re.search(r"下午", word):
            return "afternoon"
        if re.search(r"日落|傍晚|晚上|当晚", word):
            return "evening"
        return "unknown"

    def time_for_step(self, record, start, end, mention):
        left, right = clause_span(record["clean_text"], start, end, mention)
        candidates = [e for e in self.between(record, left, right) if e["entity_type"] == "TIME"
                      and self.period(e) != "unknown"]
        periods = {self.period(e) for e in candidates}
        if len(periods) != 1:
            return {"time_period": "unknown", "time_expression": None, "time": None,
                    "time_basis": "unknown", "assigned_time_entity_ids": []}
        clock = next((e for e in candidates if e["subtype"] == "clock"), None)
        clock_text = re.sub(r"\D", "", clock["text"]) if clock else None
        return {"time_period": next(iter(periods)), "time_expression": " / ".join(e["text"] for e in candidates),
                "time": clock_text[:2] + ":" + clock_text[2:] if clock_text else None,
                "time_basis": "exp02_time_same_clause", "assigned_time_entity_ids": [e["entity_id"] for e in candidates]}

    def temporal_context(self, record):
        return [{"entity_id": e["entity_id"], "day": self.day_at(record, e["end"]),
                 "time_period": self.period(e), "scope": "document_context_not_automatic_step_assignment"}
                for e in self.by_doc[record["doc_id"]] if e["entity_type"] == "TIME"]
