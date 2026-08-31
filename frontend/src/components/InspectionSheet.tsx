// frontend/src/components/InspectionSheet.tsx
import { useEffect, useState } from "react";
import {
  fetchSchema, fetchFields, gradeLookup, aggregateStructure,
  type SchemaRow, type FieldRow,
} from "../api";

interface RowState {
  member: string;
  item: string;
  subitem: string;
  measures: Record<string, string>;
  fields: FieldRow[];
  result: any;
  error?: string;
}

export function InspectionSheet() {
  const [schema, setSchema] = useState<SchemaRow[]>([]);
  const [rows, setRows] = useState<RowState[]>([]);
  const [structureType, setStructureType] = useState("거더교량 > 일반 거더교 > 일반");
  const [aggregateResult, setAggregateResult] = useState<any>(null);
  const [aggregateError, setAggregateError] = useState<string | null>(null);

  useEffect(() => {
    fetchSchema(2026).then(setSchema);
  }, []);

  const members = Array.from(new Set(schema.map((s) => s.member)));

  function addRow(member: string) {
    const first = schema.find((s) => s.member === member);
    if (!first) return;
    const newRow: RowState = {
      member, item: first.item, subitem: first.subitem,
      measures: {}, fields: [], result: null,
    };
    setRows((prev) => [...prev, newRow]);
    fetchFields(member, first.item, first.subitem)
      .then((fields) => {
        setRows((prev) =>
          prev.map((r) => (r === newRow ? { ...r, fields, error: undefined } : r)),
        );
      })
      .catch((err) => {
        setRows((prev) =>
          prev.map((r) => (r === newRow ? { ...r, error: err instanceof Error ? err.message : String(err) } : r)),
        );
      });
  }

  async function runGrade(index: number) {
    const row = rows[index];
    const measures: Record<string, number> = {};
    for (const [k, v] of Object.entries(row.measures)) {
      const num = parseFloat(v);
      if (!Number.isNaN(num)) measures[k] = num;
    }
    try {
      const result = await gradeLookup({ member: row.member, item: row.item, subitem: row.subitem, measures });
      setRows((prev) => prev.map((r, i) => (i === index ? { ...r, result, error: undefined } : r)));
    } catch (err) {
      setRows((prev) =>
        prev.map((r, i) => (i === index ? { ...r, error: err instanceof Error ? err.message : String(err) } : r)),
      );
    }
  }

  async function runAggregate() {
    const memberGrades: Record<string, string> = {};
    for (const row of rows) {
      if (row.result?.grade) memberGrades[row.member] = row.result.grade;
    }
    try {
      const result = await aggregateStructure({ structure_type: structureType, member_grades: memberGrades });
      setAggregateResult(result);
      setAggregateError(null);
    } catch (err) {
      setAggregateResult(null);
      setAggregateError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="inspection-sheet">
      <div className="member-picker">
        <select onChange={(e) => e.target.value && addRow(e.target.value)} value="">
          <option value="">+ 부재 추가</option>
          {members.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {rows.map((row, i) => (
        <div key={i} className="inspection-row">
          <strong>{row.member}</strong> / {row.item} / {row.subitem}
          {row.fields.map((f) => (
            <input
              key={f.parsed_field}
              placeholder={`${f.parsed_field}${f.parsed_unit ? ` (${f.parsed_unit})` : ""}`}
              onChange={(e) =>
                setRows((prev) =>
                  prev.map((r, idx) =>
                    idx === i ? { ...r, measures: { ...r.measures, [f.parsed_field]: e.target.value } } : r,
                  ),
                )
              }
            />
          ))}
          <button onClick={() => runGrade(i)}>등급 판정</button>
          {row.result && (
            <span className="result">
              {row.result.status === "graded" && `등급: ${row.result.grade}`}
              {row.result.status === "needs_judgment" && "정성 판단 필요 (후보 확인)"}
              {row.result.status === "no_match" && "구간 불일치"}
            </span>
          )}
          {row.error && <span className="error">오류: {row.error}</span>}
        </div>
      ))}

      <div className="structure-picker">
        <label>구조형식: </label>
        <input value={structureType} onChange={(e) => setStructureType(e.target.value)} />
        <button onClick={runAggregate}>전체 등급 계산</button>
      </div>

      {aggregateResult && (
        <div className="aggregate-result">
          환산 결함도 점수: {aggregateResult.converted_score?.toFixed(4)} → 등급: {aggregateResult.grade}
        </div>
      )}
      {aggregateError && <div className="aggregate-error">오류: {aggregateError}</div>}
    </div>
  );
}
