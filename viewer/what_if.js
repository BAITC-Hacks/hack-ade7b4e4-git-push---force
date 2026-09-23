/* Weak components include isolated remaining vertices. Each edge is counted once. */
function measureBlocking(graph, blocked = new Set()) {
  const adjacency = new Map(graph.nodes.filter(n => !blocked.has(n.id)).map(n => [n.id, []]));
  let turnover = 0, affected = 0;
  for (const edge of graph.edges) {
    turnover += edge.sum_kzt;
    if (blocked.has(edge.source) || blocked.has(edge.target)) affected += edge.sum_kzt;
    else {
      adjacency.get(edge.source).push(edge.target);
      adjacency.get(edge.target).push(edge.source);
    }
  }
  const visited = new Set();
  let fragments = 0, largest = 0;
  for (const id of adjacency.keys()) {
    if (visited.has(id)) continue;
    fragments++;
    let size = 0;
    const stack = [id];
    visited.add(id);
    while (stack.length) {
      const current = stack.pop();
      size++;
      for (const neighbor of adjacency.get(current)) {
        if (!visited.has(neighbor)) { visited.add(neighbor); stack.push(neighbor); }
      }
    }
    largest = Math.max(largest, size);
  }
  return {largest, fragments, affectedPercent: turnover > 0 ? affected / turnover * 100 : 0};
}
if (typeof module !== "undefined") module.exports = {measureBlocking};
