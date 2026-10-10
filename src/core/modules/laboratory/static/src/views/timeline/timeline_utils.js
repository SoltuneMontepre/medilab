/**
 * Puts each item on the first lane where it does not overlap the previous item, so overlapping bars stack.
 * Items need numeric `start` and `end`; returns the number of lanes used.
 */
export function assignLanes(items) {
  const laneEnds = [];
  for (const item of [...items].sort((a, b) => a.start - b.start)) {
    let lane = laneEnds.findIndex((end) => end <= item.start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(item.end);
    } else {
      laneEnds[lane] = item.end;
    }
    item.lane = lane;
  }
  return Math.max(laneEnds.length, 1);
}

export function percentOf(value, start, end) {
  return Math.min(Math.max(((value - start) / (end - start)) * 100, 0), 100);
}
