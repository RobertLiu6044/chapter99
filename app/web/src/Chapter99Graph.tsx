import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { formatRate, type GraphEdge, type RuleRow } from "./api";

type Props = {
  focus: string[];
  rules: RuleRow[];
  edges: GraphEdge[];
  baseHts: string;
};

const NODE_W = 100;
const NODE_H = 30;
const PER_COLUMN = 7;
const SUB_GAP = 118;
const COL_GAP = 250;
const MARGIN = 70;

type GNode = SimulationNodeDatum & {
  id: string;
  rank: number;
  targetX: number;
  focus: boolean;
  isBase: boolean;
};

type GLink = SimulationLinkDatum<GNode> & { edge: GraphEdge };

export function Chapter99Graph({ focus, rules, edges, baseHts }: Props) {
  const [active, setActive] = useState<string | null>(focus[0] ?? null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simRef = useRef<Simulation<GNode, GLink> | null>(null);
  const dragRef = useRef<GNode | null>(null);
  const viewRef = useRef({ x: -400, y: -220, w: 800, h: 440 });
  const [, setTick] = useState(0);

  const graph = useMemo(
    () => buildGraph(rules, edges, focus, baseHts),
    [rules, edges, focus, baseHts],
  );

  useEffect(() => {
    setActive(focus[0] ?? rules[0]?.hts ?? null);
  }, [focus, rules]);

  useEffect(() => {
    if (!graph.nodes.length) return;

    const sim = forceSimulation<GNode, GLink>(graph.nodes)
      .force(
        "link",
        forceLink<GNode, GLink>(graph.links)
          .id((d) => d.id)
          .distance(120)
          .strength(0.4),
      )
      .force("charge", forceManyBody<GNode>().strength(-420).distanceMax(600))
      // The x force is what makes this read left-to-right: every node is pulled
      // to the column for its distance from the base code.
      .force("x", forceX<GNode>((d) => d.targetX).strength(0.9))
      .force("y", forceY<GNode>(0).strength(0.06))
      .force("collide", forceCollide<GNode>(38).iterations(2))
      .alphaDecay(0.025);

    sim.on("tick", () => {
      if (!dragRef.current) fit(graph.nodes, viewRef.current);
      setTick((t) => t + 1);
    });

    simRef.current = sim;
    return () => {
      sim.stop();
      simRef.current = null;
    };
  }, [graph]);

  function toWorld(clientX: number, clientY: number) {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return null;
    return new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
  }

  function onPointerDown(e: ReactPointerEvent<SVGGElement>, node: GNode) {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    dragRef.current = node;
    setActive(node.id);
    node.fx = node.x;
    node.fy = node.y;
    simRef.current?.alphaTarget(0.25).restart();
  }

  function onPointerMove(e: ReactPointerEvent<SVGSVGElement>) {
    const node = dragRef.current;
    if (!node) return;
    const p = toWorld(e.clientX, e.clientY);
    if (!p) return;
    node.fx = p.x;
    node.fy = p.y;
  }

  function endDrag() {
    const node = dragRef.current;
    dragRef.current = null;
    if (node) {
      node.fx = null;
      node.fy = null;
    }
    simRef.current?.alphaTarget(0);
  }

  const activeRule = rules.find((r) => r.hts === active) ?? null;
  const related = edges.filter((e) => e.source === active || e.target === active);

  if (!rules.length) {
    return (
      <div className="ch99">
        <h3>Chapter 99 graph</h3>
        <p className="hint">
          No rules reference {baseHts} or its ancestors via{" "}
          <code>provided for in</code> edges.
        </p>
      </div>
    );
  }

  const view = viewRef.current;

  return (
    <div className="ch99">
      <div className="ch99-head">
        <h3>Chapter 99 graph</h3>
        <button
          type="button"
          className="ghost"
          onClick={() => {
            scatter(graph.nodes);
            simRef.current?.alpha(1).restart();
          }}
        >
          Re-run layout
        </button>
      </div>
      <p className="hint">
        A <code>d3-force</code> simulation, columned left to right by distance
        from the base code: base codes, the rules that reference them, then rules
        reached by following <code>references</code> / <code>excludes</code>{" "}
        edges. Drag any node.
      </p>

      <svg
        ref={svgRef}
        className="graph"
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Chapter 99 rule graph"
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <defs>
          {["references", "excludes"].map((kind) => (
            <marker
              key={kind}
              id={`arrow-${kind}`}
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L8,4 L0,8 z" className={`arrow ${kind}`} />
            </marker>
          ))}
        </defs>

        {graph.links.map((l) => {
          const a = l.source as GNode;
          const b = l.target as GNode;
          if (typeof a !== "object" || typeof b !== "object") return null;
          const seg = trim(a, b);
          const kind = l.edge.edge_type === "excludes" ? "excludes" : "references";
          const dim = active != null && a.id !== active && b.id !== active;
          return (
            <line
              key={`${l.edge.source}-${l.edge.target}-${l.edge.edge_type}`}
              x1={seg.x1}
              y1={seg.y1}
              x2={seg.x2}
              y2={seg.y2}
              className={`edge ${kind}${dim ? " dim" : ""}`}
              markerEnd={`url(#arrow-${kind})`}
            />
          );
        })}

        {graph.nodes.map((n) => (
          <g
            key={n.id}
            transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
            className={[
              "node",
              n.isBase ? "base" : "",
              n.focus ? "focus" : "",
              n.id === active ? "active" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onPointerDown={(e) => onPointerDown(e, n)}
          >
            <rect
              x={-NODE_W / 2}
              y={-NODE_H / 2}
              width={NODE_W}
              height={NODE_H}
              rx={n.isBase ? 13 : 4}
            />
            <text textAnchor="middle" dominantBaseline="middle">
              {n.id}
            </text>
          </g>
        ))}
      </svg>

      <div className="legend">
        <span className="swatch references" /> references
        <span className="swatch excludes" /> excludes
        <span className="swatch focus" /> references this base line
        <span className="swatch base" /> base schedule code
      </div>

      {activeRule && (
        <article className="rule-card">
          <h4>{activeRule.hts}</h4>
          <p className="meta">
            Subchapter {activeRule.subchapter} · {activeRule.rate_kind}
            {activeRule.rate_value != null
              ? ` ${formatRate(activeRule.rate_value, activeRule.rate_unit)}`
              : ""}
            {activeRule.note_ref ? ` · ${activeRule.note_ref}` : ""}
          </p>
          <p>{activeRule.description}</p>
          {related.length > 0 && (
            <ul className="edge-list">
              {related.map((e) => (
                <li key={`${e.source}-${e.target}-${e.edge_type}`}>
                  <button type="button" onClick={() => setActive(e.source)}>
                    {e.source}
                  </button>
                  <span className={`etype ${e.edge_type}`}>{e.edge_type}</span>
                  <button type="button" onClick={() => setActive(e.target)}>
                    {e.target}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </article>
      )}
    </div>
  );
}

function buildGraph(
  rules: RuleRow[],
  edges: GraphEdge[],
  focus: string[],
  baseHts: string,
) {
  const focusSet = new Set(focus);
  const ruleIds = new Set(rules.map((r) => r.hts));

  const baseIds = new Set<string>();
  for (const e of edges) {
    if (!ruleIds.has(e.target)) baseIds.add(e.target);
  }
  if (edges.some((e) => e.target === baseHts || baseHts.startsWith(e.target))) {
    baseIds.add(baseHts);
  }

  const ids = [...baseIds, ...ruleIds];
  const adj = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of edges) {
    const from = adj.get(e.source);
    const to = adj.get(e.target);
    if (!from || !to) continue;
    from.push(e.target);
    to.push(e.source);
  }

  // Rank = hop distance from the base codes, which becomes the column.
  const seeds = baseIds.size ? [...baseIds] : focus.length ? focus : ids.slice(0, 1);
  const rank = new Map<string, number>();
  const queue = seeds.filter((s) => adj.has(s));
  for (const s of queue) rank.set(s, 0);
  for (let head = 0; head < queue.length; head += 1) {
    const cur = queue[head];
    for (const nb of adj.get(cur) ?? []) {
      if (!rank.has(nb)) {
        rank.set(nb, (rank.get(cur) ?? 0) + 1);
        queue.push(nb);
      }
    }
  }
  for (const id of ids) if (!rank.has(id)) rank.set(id, 1);

  // Wide ranks are split into sub-columns so a 20-rule fan stays readable
  // instead of becoming one very tall column.
  const byRank = new Map<number, string[]>();
  for (const id of ids) {
    const r = rank.get(id) ?? 0;
    const bucket = byRank.get(r);
    if (bucket) bucket.push(id);
    else byRank.set(r, [id]);
  }
  const rankOrder = [...byRank.keys()].sort((a, b) => a - b);
  const rankX = new Map<number, number>();
  const rankSubs = new Map<number, number>();
  let cursor = 0;
  for (const r of rankOrder) {
    const count = byRank.get(r)?.length ?? 1;
    const subs = Math.max(1, Math.ceil(count / PER_COLUMN));
    rankX.set(r, cursor);
    rankSubs.set(r, subs);
    cursor += (subs - 1) * SUB_GAP + COL_GAP;
  }

  const nodes: GNode[] = [];
  for (const r of rankOrder) {
    const bucket = byRank.get(r) ?? [];
    const subs = rankSubs.get(r) ?? 1;
    bucket.forEach((id, i) => {
      const targetX = (rankX.get(r) ?? 0) + (i % subs) * SUB_GAP;
      nodes.push({
        id,
        rank: r,
        targetX,
        focus: focusSet.has(id),
        isBase: baseIds.has(id),
        x: targetX,
        y: (i - (bucket.length - 1) / 2) * 46,
      });
    });
  }

  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links: GLink[] = [];
  for (const e of edges) {
    const a = byId.get(e.source);
    const b = byId.get(e.target);
    if (!a || !b || a === b) continue;
    links.push({ source: a, target: b, edge: e });
  }

  return { nodes, links };
}

function scatter(nodes: GNode[]) {
  for (const n of nodes) {
    n.x = n.targetX + (Math.random() - 0.5) * 80;
    n.y = (Math.random() - 0.5) * 320;
    n.vx = 0;
    n.vy = 0;
  }
}

/** Keep the whole graph in frame: fit the viewBox to the node extents. */
function fit(nodes: GNode[], view: { x: number; y: number; w: number; h: number }) {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const n of nodes) {
    const x = n.x ?? 0;
    const y = n.y ?? 0;
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  if (!Number.isFinite(minX)) return;

  const target = {
    x: minX - MARGIN,
    y: minY - MARGIN,
    w: Math.max(480, maxX - minX + MARGIN * 2),
    h: Math.max(300, maxY - minY + MARGIN * 2),
  };
  // Ease toward the target so the frame glides instead of snapping each tick.
  view.x += (target.x - view.x) * 0.2;
  view.y += (target.y - view.y) * 0.2;
  view.w += (target.w - view.w) * 0.2;
  view.h += (target.h - view.h) * 0.2;
}

function trim(a: GNode, b: GNode) {
  const ax = a.x ?? 0;
  const ay = a.y ?? 0;
  const bx = b.x ?? 0;
  const by = b.y ?? 0;
  const dx = bx - ax;
  const dy = by - ay;
  const d = Math.hypot(dx, dy) || 0.01;
  const ux = dx / d;
  const uy = dy / d;
  // Radius of the node box along this direction, so edges stop at its border.
  const r = 1 / Math.hypot(ux / (NODE_W / 2 + 4), uy / (NODE_H / 2 + 4));
  return { x1: ax + ux * r, y1: ay + uy * r, x2: bx - ux * r, y2: by - uy * r };
}
