// frontend/src/api.ts
const API_BASE = "http://localhost:8000";

export async function sendChat(message: string): Promise<string> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`chat 요청 실패: ${res.status}`);
  const data = await res.json();
  return data.answer as string;
}

export interface GradeRequest {
  member: string;
  item: string;
  subitem?: string;
  measures: Record<string, number>;
  year?: number;
}

export async function gradeLookup(payload: GradeRequest) {
  const res = await fetch(`${API_BASE}/inspection/grade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`등급 조회 실패: ${res.status}`);
  return res.json();
}

export interface SchemaRow {
  member: string;
  item: string;
  subitem: string;
}

export async function fetchSchema(year = 2026): Promise<SchemaRow[]> {
  const res = await fetch(`${API_BASE}/inspection/schema?year=${year}`);
  if (!res.ok) throw new Error(`기준표 조회 실패: ${res.status}`);
  return res.json();
}

export interface FieldRow {
  parsed_field: string;
  parsed_unit: string | null;
}

export async function fetchFields(
  member: string, item: string, subitem: string, year = 2026,
): Promise<FieldRow[]> {
  const params = new URLSearchParams({ member, item, subitem, year: String(year) });
  const res = await fetch(`${API_BASE}/inspection/fields?${params}`);
  if (!res.ok) throw new Error(`입력항목 조회 실패: ${res.status}`);
  return res.json();
}

export interface AggregateStructureRequest {
  year?: number;
  structure_type: string;
  member_grades: Record<string, string>;
  critical_defect_member?: string;
}

export async function aggregateStructure(payload: AggregateStructureRequest) {
  const res = await fetch(`${API_BASE}/inspection/aggregate-structure`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`전체 등급 계산 실패: ${res.status}`);
  return res.json();
}
