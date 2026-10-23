// Every seat of the office: desk chairs, Fika seats, and the infirmary bed (architecture Section 6.2).
// Fields: id (room and index), scene, position (seat anchor in percent of the artwork: x of width, y of height),
// depth (stacking order of the seated figure), facing, approach (the floor.js waypoint on the seat's free side, where
// a walker stands before sitting down and after getting up: behind a rear-facing desk chair, behind the desk for a
// front-facing one, in front of a sofa cushion or the armchair seat, beside the bed),
// footprints (the floor.js footprints of its chair, sofa, or bed and, at a desk, the desk; the step between the
// approach and the seat touches no other footprint), and at a desk the workstation points (left hand on the keyboard,
// pointer hand on the keyboard, mouse) and the visible screen glass, both in artwork pixels.
// Facings are those the sprites support: "front" (seated front frame), "back" (seated rear frame), their mirrors
// "front-right" and "back-left", and "lying" for the bed.
export const SEATS = [
  { id: "studio0.0", scene: "main", position: [26.5,36.5], depth: 38, facing: "back", approach: "s0a",
    footprints: ["studio-chair-near-a", "studio-desk"], workstation: [[397,325],[417,332],[438,333]],
    screen: "405,257 453,277 453,308 404,290" },
  { id: "studio0.1", scene: "main", position: [36,42], depth: 44, facing: "back", approach: "s0b",
    footprints: ["studio-chair-near-b", "studio-desk"], workstation: [[548,374],[570,381],[599,387]],
    screen: "555,312 605,327 605,363 555,347" },
  // Front-facing desks hide their screens.
  { id: "studio0.2", scene: "main", position: [32.4,26.2], depth: 25, facing: "front", approach: "s0g",
    footprints: ["studio-chair-far-a", "studio-desk"], workstation: [[478,265],[495,271],[515,280]], screen: null },
  { id: "studio0.3", scene: "main", position: [42.5,32.2], depth: 30, facing: "front", approach: "s0f",
    footprints: ["studio-chair-far-b", "studio-desk"], workstation: [[622,316],[641,325],[663,333]], screen: null },
  { id: "studio1.0", scene: "main", position: [75.2,37.8], depth: 41, facing: "back", approach: "s1a",
    footprints: ["studio1-chair-a", "studio1-desk"], workstation: [[1148,341],[1169,350],[1191,353]],
    screen: "1147,287 1190,302 1190,333 1147,317" },
  { id: "studio1.1", scene: "main", position: [83.8,43.4], depth: 47, facing: "back", approach: "s1b",
    footprints: ["studio1-chair-b", "studio1-desk"], workstation: [[1275,391],[1296,401],[1320,411]],
    screen: "1270,337 1313,352 1313,385 1270,370" },
  { id: "common.0", scene: "main", position: [13.3,59.7], depth: 62, facing: "back", approach: "k0",
    footprints: ["common-chair-a", "common-desk"], workstation: [[196,556],[216,566],[241,573]],
    screen: "202,493 247,511 247,546 202,528" },
  { id: "common.1", scene: "main", position: [21.8,64.4], depth: 67, facing: "back", approach: "k1",
    footprints: ["common-chair-b", "common-desk"], workstation: [[329,607],[351,616],[377,624]],
    screen: "328,541 378,558 378,592 328,574" },
  // Fika: the left sofa cushion, the armchair (rear-facing, drawn mirrored), and the right sofa cushion.
  { id: "fika.0", scene: "main", position: [49.5,66.9], depth: 70, facing: "front", approach: "f0",
    footprints: ["sofa"], workstation: null, screen: null },
  { id: "fika.1", scene: "main", position: [58.7,80.6], depth: 82, facing: "back-left", approach: "f3",
    footprints: ["lounge-chair"], workstation: null, screen: null },
  { id: "fika.2", scene: "main", position: [56.7,70.6], depth: 73, facing: "front", approach: "f2",
    footprints: ["sofa"], workstation: null, screen: null },
  // The bed is entered from its side, where the colleague stands before lying down.
  { id: "infirmary.0", scene: "main", position: [85.9,63.5], depth: 74, facing: "lying", approach: "i3",
    footprints: ["bed"], workstation: null, screen: null },
];

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
  return [seat.position[0], seat.position[1] + (rearFacing(seat.facing) ? 2.2 : 3.6)];
}
