// Desk visits retain their places; newcomers use their Project area before shared vacancies.
export function reserveDesks(previous, people, seats, preferred, meetingMembers = new Set()) {
  const valid = new Set(seats.map((seat) => seat.id)), present = new Set(people.map((row) => row.key));
  const occupants = new Map([...previous].filter(([key]) => present.has(key)));
  for (const row of people) if (!occupants.has(row.key)) occupants.set(row.key, null);
  const taken = new Set();
  for (const [key, id] of occupants) {
    if (id === null) continue;
    if (!valid.has(id) || taken.has(id)) occupants.set(key, null);
    else taken.add(id);
  }
  for (const ownArea of [true, false]) for (const [key, id] of occupants) {
    if (id !== null || meetingMembers.has(key)) continue;
    const room = preferred.get(key);
    const free = seats.find((seat) => !taken.has(seat.id) && (!ownArea || seat.id.startsWith(room + ".")));
    if (!free) continue;
    occupants.set(key, free.id); taken.add(free.id);
  }
  return occupants;
}
