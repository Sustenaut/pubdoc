// Shared MyST plugin for the verdict-coded annotation scheme (see
// AGENTS.md, "Annotation scheme"). Referenced by any doc's myst.yml via
// `project.plugins: [../.pubdoc/templates/annotations.mjs]`.
//
// Provides four inline roles - {true}, {partial}, {false}, {neutral} -
// each taking a short, stable NAME (not a number) as their body, e.g.:
//
//   The essay claims X {true}`sons-mortality`.
//
// A name can be reused anywhere in the document to mark a second mention
// of the same claim; it always resolves to the same note number. Numbers
// are assigned automatically, in the order names first appear in the
// text - never typed by hand, so inserting/removing/reordering notes
// never requires renumbering anything.
//
// Each name needs exactly one matching heading elsewhere in the document
// (normally in a "## Notes" section) labeled with `(note-<name>)=` and
// containing the literal text "Note" - the transform below rewrites that
// text to "Note <n>" using the same number, so the in-text marker and
// its target always agree:
//
//   (note-sons-mortality)=
//   ### Note
//
//   :::{warning} Verdict: Partially true - "..."
//   ...
//   :::
//
// Colors match exactly what myst-imports.typ's admonition() helper uses
// for each color's own left-border stroke (color.darken(20%)) - see
// AGENTS.md for why plain Unicode symbols need this (no inherent color,
// unlike emoji) and why {raw:typst} is the only way to get real color
// with no native MyST color role.
const VERDICTS = {
  true: { color: 'green', symbol: '✓' },
  partial: { color: 'yellow', symbol: '◪' },
  false: { color: 'red', symbol: '✗' },
  neutral: { color: 'blue', symbol: '☐' },
};

function verdictRole(name) {
  return {
    name,
    body: { type: String, required: true },
    run(data) {
      return [{ type: 'verdictMark', verdict: name, name: data.body }];
    },
  };
}

function isVerdictMark(node) {
  return node && node.type === 'verdictMark';
}

function walk(node, visit) {
  visit(node);
  if (Array.isArray(node.children)) {
    node.children.forEach((child) => walk(child, visit));
  }
}

const annotationsPlugin = {
  name: 'Verdict-coded annotations',
  roles: Object.keys(VERDICTS).map(verdictRole),
  transforms: [
    {
      name: 'verdict-annotations',
      doc: 'Auto-number {true}/{partial}/{false}/{neutral} markers by first appearance and color-code them; sync the matching Note heading text to the same number.',
      stage: 'document',
      plugin: () => (tree) => {
        // Pass 1: assign numbers to each unique name, in document order.
        const numberByName = new Map();
        walk(tree, (node) => {
          if (!isVerdictMark(node)) return;
          if (!numberByName.has(node.name)) {
            numberByName.set(node.name, numberByName.size + 1);
          }
        });

        // Pass 2: replace each verdictMark node in place with the
        // rendered marker (mutate type/children directly - it's the
        // same object reference the tree already holds).
        walk(tree, (node) => {
          if (!isVerdictMark(node)) return;
          const n = numberByName.get(node.name);
          const { color, symbol } = VERDICTS[node.verdict];
          const url = `#note-${node.name}`;
          const iconRaw = { type: 'raw', lang: 'typst', typst: `#text(fill: ${color}.darken(20%))[${symbol}]` };
          node.type = 'link';
          node.url = url;
          node.children = [
            { type: 'text', value: `[${n}` },
            iconRaw,
            { type: 'text', value: ']' },
          ];
          delete node.verdict;
          delete node.name;
        });

        // Pass 3: sync each labeled "Note" heading's text to the number
        // assigned to its name.
        walk(tree, (node) => {
          if (node.type !== 'heading') return;
          const id = node.identifier || node.html_id || node.label;
          if (!id || !id.startsWith('note-')) return;
          const name = id.slice('note-'.length);
          const n = numberByName.get(name);
          if (n === undefined) return;
          node.children = [{ type: 'text', value: `Note ${n}` }];
        });
      },
    },
  ],
};

export default annotationsPlugin;
