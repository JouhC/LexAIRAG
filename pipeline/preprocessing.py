import json
import re

division_pattern = re.compile(r'\n([A-Z ]+DIVISION)\n')

def cut_before_division(text: str) -> str:
    m = division_pattern.search(text)
    if not m:
        return text
    return text[m.start()+1:].lstrip()

def main():
    with open('../data/sc_elibrary_decisions_text_combined.jsonl', "r", encoding="utf-8") as fin, \
        open('../data/sc_elibrary_decisions_text_combined_cleaned.jsonl', "w", encoding="utf-8") as fout:
        for line in fin:
            obj = json.loads(line)

            if "text" in obj:
                obj["text"] = cut_before_division(obj["text"])

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()