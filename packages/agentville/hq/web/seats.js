// Seat anchors, approaches and workstation targets use the shared artwork measurements.
import { SEATS } from "./office-layout.js";
import { seatedFootOffset } from "./layout.js";
export { SEATS };

export const roomOfSeat = (seat) => seat.id.slice(0, seat.id.lastIndexOf("."));
export const indexOfSeat = (seat) => Number(seat.id.slice(seat.id.lastIndexOf(".") + 1));
// The seats of one room in seat-number order; arrivals take the lowest free one.
export function roomSeats(room) {
  return SEATS.filter((seat) => roomOfSeat(seat) === room).sort((a, b) => indexOfSeat(a) - indexOfSeat(b));
}

// Rear-facing seats use the seated rear frame; mirrored facings draw the sprite flipped left to right.
export const rearFacing = (facing) => facing === "back" || facing === "back-left";
export const frontFacing = (facing) => facing === "front" || facing === "front-right";
export const mirroredFacing = (facing) => facing === "back-left" || facing === "front-right";
// Where the feet of a seated figure rest, in front of the chair or cushion; the step to the approach starts here.
export function seatFoot(seat) {
  return [seat.position[0], seat.position[1] + seatedFootOffset(rearFacing(seat.facing))];
}
