// Plain-text export of a CV for pasting into LinkedIn, which renders no
// Markdown and no links in most fields. Usage:
//
//   ./pubdoc linkedin cv/index.md > linkedin.txt
//
// which runs this file from the repo's .pubdoc/templates/, in the repo's
// root, so pub-plugin.mjs finds that repo's publets-local.json.
//
// Reads the same index.md the PDF is built from, resolves {pub} tags via
// the shared publet registry, and prints (1) a deduplicated skills list
// and (2) one block per Employment entry: company, title, dates,
// per-role skills (its "Key technologies" line), and the bullets as the
// description, with a character count against LinkedIn's 2000 limit.
// Only `# Employment` sections are read - not Vendor Management,
// Education, or Summary.
import fs from 'node:fs';
import { resolvePub } from './pub-plugin.mjs';

const DESCRIPTION_LIMIT = 2000;
const SKILLS_LIMIT = 50;

const file = process.argv[2];
if (!file) {
  console.error('usage: node linkedin-text.mjs <path/to/index.md>');
  process.exit(1);
}

const PUB = /\{pub\}`([^`]+)`/g;

// Skill names are always the singular form, even where the CV says "LLMs".
function pubTexts(line) {
  return [...line.matchAll(PUB)].map((m) => {
    const { publet, text, localName } = resolvePub(m[1].replace(/\+$/, ''));
    if (!publet) throw new Error(`unknown {pub} name "${localName}"`);
    return text;
  });
}

function plain(line) {
  return line
    .replace(PUB, (_, body) => {
      const { publet, text, localName } = resolvePub(body);
      if (!publet) throw new Error(`unknown {pub} name "${localName}"`);
      return text;
    })
    .replace(/\*+/g, '')
    .replace(/\\\$/g, '$')
    .trim();
}

const lines = fs.readFileSync(file, 'utf8').split('\n');
const entries = [];
const skillCounts = new Map(); // lowercase text -> { text, count, first }
let order = 0;
function noteSkill(text) {
  const k = text.toLowerCase();
  const cur = skillCounts.get(k) ?? { text, count: 0, first: order++ };
  cur.count += 1;
  skillCounts.set(k, cur);
}

let section = null;
let current = null;
let bullet = null;
for (const raw of lines) {
  const h = raw.match(/^# (.+)$/);
  if (h) {
    section = h[1].trim();
    current = bullet = null;
    continue;
  }
  if (section === 'Technical Skills') {
    for (const t of pubTexts(raw)) noteSkill(t);
    continue;
  }
  if (section !== 'Employment') continue;

  const head = raw.match(/^\*\*(.+?)\*\*\s*(.*)$/);
  if (head && !head[1].startsWith('Key technologies')) {
    const full = head[1];
    const cut = full.lastIndexOf(',');
    current = {
      company: cut === -1 ? full : full.slice(0, cut).trim(),
      title: cut === -1 ? '' : full.slice(cut + 1).trim(),
      dates: head[2].trim().replace(/\.$/, ''),
      skills: [],
      bullets: [],
    };
    entries.push(current);
    bullet = null;
    continue;
  }
  if (!current) continue;
  if (raw.startsWith('**Key technologies:**')) {
    current.skills = pubTexts(raw);
    current.skills.forEach((t) => noteSkill(t));
    bullet = null;
    continue;
  }
  if (raw.startsWith('- ')) {
    bullet = plain(raw.slice(2));
    current.bullets.push(bullet);
  } else if (/^\s+\S/.test(raw) && bullet !== null) {
    current.bullets[current.bullets.length - 1] += ' ' + plain(raw);
  } else {
    bullet = null;
  }
}

const skills = [...skillCounts.values()].sort((a, b) => b.count - a.count || a.first - b.first);
const out = [];
out.push(`SKILLS (${skills.length} of LinkedIn's ${SKILLS_LIMIT} max) - add one at a time, most-used first`);
out.push('');
skills.forEach((s) => out.push(s.text));

for (const e of entries) {
  const description = e.bullets.map((b) => `• ${b}`).join('\n');
  const n = description.length;
  out.push('', '='.repeat(60));
  out.push(`Company: ${e.company}`);
  out.push(`Title:   ${e.title}`);
  out.push(`Dates:   ${e.dates}`);
  if (e.skills.length) out.push(`Skills:  ${e.skills.join(', ')}`);
  out.push('', `Description (${n}/${DESCRIPTION_LIMIT} chars${n > DESCRIPTION_LIMIT ? ' - TOO LONG' : ''}):`);
  out.push(description);
}
console.log(out.join('\n'));
