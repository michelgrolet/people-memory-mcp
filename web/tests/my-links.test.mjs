import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const start = html.indexOf('let nodes = [], links = []');
const end = html.indexOf('function setTreeMode(', start);
function graph(show, email = 'owner@example.test') {
  const people = [
    { id: 1, name: 'Alex Example', identifiers: [{ kind: 'email', value: 'OWNER@example.test' }] },
    { id: 2, name: 'Blair Example' }, { id: 3, name: 'Casey Example' },
  ];
  const DATA = { people, orgs: [{ id: 4, name: 'Example Org' }], affs: [{ person_id: 1, org_id: 4 }, { person_id: 2, org_id: 4 }], edges: [{ a: 1, b: 2, kind: 'friend' }, { a: 3, b: 1, kind: 'friend' }, { a: 2, b: 3, kind: 'knows' }] };
  const ctx = vm.createContext({ DATA, byId: new Map(people.map(p => [p.id,p])), myEmail: email, ALL_TIES: [] });
  vm.runInContext(html.slice(start, end), ctx);
  if (show) vm.runInContext('showMyLinks = true', ctx);
  vm.runInContext('buildGraph()', ctx);
  return JSON.parse(vm.runInContext('JSON.stringify({ links: links.map(l => [nodes[l.s].id, nodes[l.t].id]), people: nodes.filter(n => n.type === "person").map(n => n.id), edges: DATA.edges })', ctx));
}
test('default graph hides both directions and organization links for the account holder', () => {
  const result = graph(false);
  assert.deepEqual(result.links, [[2,4], [2,3]]);
  assert.deepEqual(result.people.sort(), [1,2,3]);
  assert.equal(result.edges.length, 3);
});
test('Show my links restores all five links', () => assert.equal(graph(true).links.length, 5));
test('unmatched account keeps all links', () => assert.equal(graph(false, 'unknown@example.test').links.length, 5));
