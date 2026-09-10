"""从已下载的公开 kiwi/strings/arena JSON 构建内置描述。

输入文件：kiwi.json、strings.json、arena.json（可选）。来源见 README。
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.augment_descriptions import build_rows

parser = argparse.ArgumentParser()
parser.add_argument('--source-dir', type=Path, required=True)
args = parser.parse_args()
def read(name):
    path = args.source_dir / (name + '.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
rows = build_rows(read('kiwi'), read('strings'), read('arena'))
output = ROOT / 'app/ui/augment-descriptions.json'
output.write_text(json.dumps({'fetchedAt': date.today().isoformat(), 'source': 'CommunityDragon', 'rows': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
print('Descriptions built:', len(rows), 'with dynamic values:', sum(r['dynamicValues'] for r in rows.values()))
