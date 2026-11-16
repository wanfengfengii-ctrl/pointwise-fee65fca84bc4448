"""Print real literal hits and their original source tokens."""
import json

from samples import DOCUMENTS
from tokenphrase import Corpus


def main() -> None:
    corpus = Corpus(DOCUMENTS)
    reports = []
    for query in (["心肌", "梗死"], ["心梗"], ["患者", "需要"], ["复查", "复查"], ["边界", "不可"]):
        reports.append({
            "query": query,
            "hits": [
                {"doc_id": doc_id, "start": start, "end": end,
                 "tokens": list(corpus.evidence((doc_id, start, end)))}
                for doc_id, start, end in corpus.find(query)
            ],
        })
    print(json.dumps({"mode": "literal", "reports": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
