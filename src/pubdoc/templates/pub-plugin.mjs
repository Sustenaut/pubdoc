// Shared MyST plugin: a central publet registry, usable by any document.
//
// A "publet" is a short, standalone reference to one concept (a
// technology, standard, or company) - its own small Markdown file under
// publets/, with frontmatter (id, url, text, optional plural) plus a
// one-paragraph synopsis as the body. Two-level indirection, on purpose:
//
//   {pub}`key` in index.md
//     -> publets-local.json maps "key" to a global id (stable even if
//        the key, the file it lives in, or its display text changes)
//     -> publets/<some-file>.md with that id is the actual publet
//
// Why two levels instead of one flat registry (the old links.json): a
// publet's *id* is what makes it "the same Python reference" everywhere
// it's used, independent of what any one document calls it.
// publets-local.json is the consuming repo's own shared namespace of
// short names for the publets actually used across every doc there -
// one file, not one per document - so cv/ and cover-letter/ both
// resolve `python` through the same local name.
//
// publets/ and publets-local.json are content, so they live in the
// consuming repo, not in pubdoc: the plugin walks up from the current
// directory (the doc directory, where `pubdoc build` runs curvenote) to
// the first directory holding a publets-local.json, and reads
// publets/ next to it.
//
// Local names are lowercase; the lookup lowercases the call's name so
// {pub}`TiDB` and {pub}`tidb` are the same thing.
//
// A trailing `+` on the role body requests the plural form, computed as
// `entry.plural ?? (entry.text + "s")` - no second registry entry, no
// duplicated url/id: {pub}`llm+` renders "LLMs".
//
// The publet's synopsis becomes the link's `title` - the same mdast
// field a literal `[text](url "title")` sets - so it needs no
// Typst/HTML-specific handling: HTML renders it as a hover tooltip,
// Typst's exporter just ignores an mdast field it doesn't use (no
// visible change in the PDF).
import fs from 'node:fs';
import path from 'node:path';

function findRegistryRoot(start) {
  for (let dir = path.resolve(start); ; dir = path.dirname(dir)) {
    if (fs.existsSync(path.join(dir, 'publets-local.json'))) return dir;
    if (path.dirname(dir) === dir) {
      throw new Error(`pub-plugin: no publets-local.json in ${start} or any parent directory`);
    }
  }
}

const registryRoot = findRegistryRoot(process.cwd());

function parsePubletFile(filePath) {
  const lines = fs.readFileSync(filePath, 'utf8').split('\n');
  if (lines[0].trim() !== '---') {
    throw new Error(`${filePath}: expected frontmatter delimited by "---"`);
  }
  const frontmatter = {};
  let i = 1;
  for (; i < lines.length && lines[i].trim() !== '---'; i++) {
    const line = lines[i];
    const sep = line.indexOf(': ');
    if (sep === -1) continue;
    frontmatter[line.slice(0, sep).trim()] = line.slice(sep + 2).trim();
  }
  const synopsis = lines.slice(i + 1).join('\n').trim();
  return { ...frontmatter, id: Number(frontmatter.id), synopsis };
}

const publetsDir = path.join(registryRoot, 'publets');
const publetsById = new Map();
for (const filename of fs.readdirSync(publetsDir)) {
  if (!filename.endsWith('.md')) continue;
  const publet = parsePubletFile(path.join(publetsDir, filename));
  publetsById.set(publet.id, publet);
}

const localRegistry = JSON.parse(
  fs.readFileSync(path.join(registryRoot, 'publets-local.json'), 'utf8'),
);

// Shared lookup, also used by linkedin-text.mjs: resolves a {pub} body
// ("key" or "key+") to its publet and display text, or null if unknown.
export function resolvePub(body) {
  const wantsPlural = body.endsWith('+');
  const localName = wantsPlural ? body.slice(0, -1) : body;
  const id = localRegistry[localName.toLowerCase()];
  const publet = id === undefined ? undefined : publetsById.get(id);
  if (!publet) return { localName, publet: null, text: null };
  const text = wantsPlural ? (publet.plural ?? `${publet.text}s`) : publet.text;
  return { localName, publet, text };
}

function publetRole() {
  return {
    name: 'pub',
    body: { type: String, required: true },
    run(data) {
      const { localName, publet, text } = resolvePub(data.body);
      if (!publet) {
        // Visibly broken in every export rather than silently vanishing,
        // so a typo'd local name is obvious at a glance.
        return [{ type: 'text', value: `[[pub: unknown local name "${localName}"]]` }];
      }
      const node = { type: 'link', url: publet.url, children: [{ type: 'text', value: text }] };
      if (publet.synopsis) node.title = publet.synopsis;
      return [node];
    },
  };
}

const pubPlugin = {
  name: 'Central publet registry',
  roles: [publetRole()],
};

export default pubPlugin;
