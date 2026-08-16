import { displayHts, formatRate, type HtsRow } from "./api";

type Props = {
  parents: HtsRow[];
  selected: HtsRow;
  childRows: HtsRow[];
  onSelect: (hts: string) => void;
};

const LEVELS = [
  { name: "Grouping", digits: "no code of its own" },
  { name: "Heading", digits: "4-digit" },
  { name: "Subheading", digits: "6-digit" },
  { name: "Tariff line", digits: "8-digit" },
  { name: "Statistical suffix", digits: "10-digit" },
];

export function HierarchyPanel({
  parents,
  selected,
  childRows,
  onSelect,
}: Props) {
  // parents arrive root-first, so this is the full path down to the selection.
  const path = [...parents, selected];
  const chapter = chapterOf(selected);

  function renderPath(index: number) {
    const row = path[index];
    const isSelected = index === path.length - 1;
    const deeper = index + 1 < path.length;

    return (
      <li key={row.hts} className={isSelected ? "branch current" : "branch"}>
        <Row
          row={row}
          selected={isSelected}
          onSelect={isSelected ? undefined : onSelect}
        />
        {(deeper || isSelected) && (
          <ul>
            {deeper && renderPath(index + 1)}
            {isSelected && renderChildren()}
          </ul>
        )}
      </li>
    );
  }

  function renderChildren() {
    if (!childRows.length) {
      return (
        <li className="branch">
          <p className="leaf-note">
            No deeper subdivisions — this is a leaf line of the schedule.
          </p>
        </li>
      );
    }
    return (
      <>
        <li className="branch label">
          <p className="child-label">
            {childRows.length} child {childRows.length === 1 ? "row" : "rows"}
            {" one level deeper"}
          </p>
        </li>
        {childRows.map((c) => (
          <li key={c.hts} className="branch">
            <Row row={c} onSelect={onSelect} />
          </li>
        ))}
      </>
    );
  }

  return (
    <div className="hierarchy">
      <h3>Schedule hierarchy</h3>
      <p className="hint">
        Each level below is one segment longer than the level above it. The
        highlighted row is your selection; rows nested under it are its direct
        children.
      </p>

      <nav className="crumbs" aria-label="HTS path">
        {chapter && <span className="crumb chapter">Chapter {chapter}</span>}
        {path.map((row, i) => (
          <span key={row.hts} className="crumb-group">
            <span className="sep" aria-hidden="true">
              ›
            </span>
            {i === path.length - 1 ? (
              <span className="crumb here">{displayHts(row)}</span>
            ) : (
              <button
                type="button"
                className="crumb"
                onClick={() => onSelect(row.hts)}
              >
                {displayHts(row)}
              </button>
            )}
          </span>
        ))}
      </nav>

      <ul className="tree">{renderPath(0)}</ul>
    </div>
  );
}

function Row({
  row,
  selected = false,
  onSelect,
}: {
  row: HtsRow;
  selected?: boolean;
  onSelect?: (hts: string) => void;
}) {
  const level = LEVELS[levelIndex(row)];
  const body = (
    <>
      <span className="row-top">
        <span className={row.superior ? "code grouping" : "code"}>
          {displayHts(row)}
        </span>
        <span className="lvl" title={level.digits}>
          {level.name}
        </span>
        {selected && <span className="here-tag">you are here</span>}
      </span>
      <span className="rate">{formatRate(row.mfn_rate, row.mfn_rate_unit)}</span>
      <span className="desc">{row.description || "—"}</span>
    </>
  );

  if (!onSelect) {
    return <div className="row static">{body}</div>;
  }
  return (
    <button type="button" className="row" onClick={() => onSelect(row.hts)}>
      {body}
    </button>
  );
}

function levelIndex(row: HtsRow): number {
  if (row.code[0] === 0) return 0;
  return row.code.filter((seg) => seg >= 0).length;
}

function chapterOf(row: HtsRow): string | null {
  const heading = row.code[0];
  if (!heading || heading <= 0) return null;
  return String(Math.floor(heading / 100)).padStart(2, "0");
}
