// 경보 ↔ 인사이트 상호 연결 해석(순수 로직 → 단위 테스트 대상).

// id로 항목을 찾는다. 없으면 undefined.
export function findById<T extends { id: string }>(items: T[], id: string): T | undefined {
  return items.find((item) => item.id === id);
}

// linked id 목록을 실제 항목 배열로 해석한다. 존재하지 않는 id는 제외(순서 유지).
export function resolveLinked<T extends { id: string }>(ids: string[], items: T[]): T[] {
  return ids.map((id) => findById(items, id)).filter((item): item is T => item !== undefined);
}
