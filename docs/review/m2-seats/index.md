# M2 Sixty-Seat Owner Review

Owner review set for the sixty-seat office of f323b87 under decision D13 of the [0.4.0 milestone record](../../milestone-0.4.0.md#post-closure-office-change). Status: owner review pending.

## Method

- Captures use Chromium at a 1440 px viewport with device scale 2 and reduced motion, through the real HQ page. Each tile is cut around the seat's measured hip point (140 x 156 source pixels); the red marker on the top edge is above that point. Seat ids are captioned below each tile; in-page labels are hidden so they do not cover heads.
- Desks (sheets 01, 02): live HQ with 20 working colleagues and no Contractors, so hands reach keyboard and mouse.
- Meeting rooms and Fika (sheets 03 to 05): the full-seat demonstration `/?demo=seats`, every place occupied at once (meeting colleagues working or thinking, Fika colleagues idle with drinks or books).
- Desks with the Contractor team away (sheet 06): live HQ, four runs of five colleagues with one Contractor each; after 10 s each team works in a meeting room or Fika group and its desk stays reserved and empty.
- Contractor teams (sheet 07): live HQ with six teams (5, 5, 7, 7, 2 and 2 Contractors) after 10 s; rear-facing Contractors are smaller than the chair backs in front of them, so mostly their hats show; check that this reads acceptably.
- Sheets are palette-quantized PNG (128 colours). No artwork was drawn or changed; the tiles show the existing images as rendered.

## Sheets

| Sheet | Content |
| --- | --- |
| [01-window-desks.png](01-window-desks.png) | studio0.0-3, studio1.0-3, studio2.0-3, occupied by working colleagues |
| [02-center-desks.png](02-center-desks.png) | studio3.0-7, occupied by working colleagues |
| [03-meeting-rooms.png](03-meeting-rooms.png) | meeting.0-5 and meeting-east.0-5, occupied |
| [04-fika-tables.png](04-fika-tables.png) | fika.0-15 (two Fika tables), occupied |
| [05-sofas-high-tables.png](05-sofas-high-tables.png) | fika.16-21 (sofas) and fika.22-27 (high tables), occupied |
| [06-desks-team-away.png](06-desks-team-away.png) | All 20 desks while the occupant's Contractor team is away |
| [07-contractor-teams.png](07-contractor-teams.png) | Six Contractor teams filling all 12 meeting chairs and the 22 Fika table and sofa places (D14): seated Contractors at Contractor scale with hard hats |

## Seats

For every seat also check that no body part clips through furniture that stands in front of it, and that the figure is not hidden by furniture that stands behind it.

| Seat | Source id | Area | Facing | Sheets | What to check |
| --- | --- | --- | --- | --- | --- |
| studio0.0 | window-left.0 | Window desks, left | back | 01, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio0.1 | window-left.1 | Window desks, left | back | 01, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio0.2 | window-left.2 | Window desks, left | front | 01, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| studio0.3 | window-left.3 | Window desks, left | front | 01, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| studio1.0 | window-middle.0 | Window desks, middle | back | 01, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio1.1 | window-middle.1 | Window desks, middle | back | 01, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio1.2 | window-middle.2 | Window desks, middle | front | 01, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| studio1.3 | window-middle.3 | Window desks, middle | front | 01, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| studio2.0 | window-right.0 | Window desks, right | back | 01, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio2.1 | window-right.1 | Window desks, right | back | 01, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio2.2 | window-right.2 | Window desks, right | front | 01, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| studio2.3 | window-right.3 | Window desks, right | front | 01, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| studio3.0 | center.0 | Center desks | back | 02, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio3.1 | center.1 | Center desks | back | 02, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio3.2 | center.2 | Center desks | back | 02, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio3.3 | center.3 | Center desks | back | 02, 06 | Faces the monitor; both hands on keyboard and mouse; back to the viewer, feet forward under the desk, chair back in front of the body; with the team away the desk is empty and nobody else sits there |
| studio3.4 | center.4 | Center desks | front | 02, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| studio3.5 | center.5 | Center desks | front | 02, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| studio3.6 | center.6 | Center desks | front | 02, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| studio3.7 | center.7 | Center desks | front | 02, 06 | Faces the monitor; both hands on keyboard and mouse; faces the viewer from behind the desk, legs under the desk, monitor in front; with the team away the desk is empty and nobody else sits there |
| meeting.0 | meeting-north.0 | Meeting room, north | back | 03 | Faces the table; back to the viewer, feet under the table, chair back in front; no keyboard gesture |
| meeting.1 | meeting-north.1 | Meeting room, north | back | 03 | Faces the table; back to the viewer, feet under the table, chair back in front; no keyboard gesture |
| meeting.2 | meeting-north.2 | Meeting room, north | back | 03 | Faces the table; back to the viewer, feet under the table, chair back in front; no keyboard gesture |
| meeting.3 | meeting-north.3 | Meeting room, north | front | 03 | Faces the table; faces the viewer across the table, feet under the table; no keyboard gesture |
| meeting.4 | meeting-north.4 | Meeting room, north | front | 03 | Faces the table; faces the viewer across the table, feet under the table; no keyboard gesture |
| meeting.5 | meeting-north.5 | Meeting room, north | front | 03 | Faces the table; faces the viewer across the table, feet under the table; no keyboard gesture |
| meeting-east.0 | meeting-east.0 | Meeting room, east | back | 03 | Faces the table; back to the viewer, feet under the table, chair back in front; no keyboard gesture |
| meeting-east.1 | meeting-east.1 | Meeting room, east | back | 03 | Faces the table; back to the viewer, feet under the table, chair back in front; no keyboard gesture |
| meeting-east.2 | meeting-east.2 | Meeting room, east | back | 03 | Faces the table; back to the viewer, feet under the table, chair back in front; no keyboard gesture |
| meeting-east.3 | meeting-east.3 | Meeting room, east | front | 03 | Faces the table; faces the viewer across the table, feet under the table; no keyboard gesture |
| meeting-east.4 | meeting-east.4 | Meeting room, east | front | 03 | Faces the table; faces the viewer across the table, feet under the table; no keyboard gesture |
| meeting-east.5 | meeting-east.5 | Meeting room, east | front | 03 | Faces the table; faces the viewer across the table, feet under the table; no keyboard gesture |
| fika.0 | fika-north.0 | Fika table, north | back | 04 | Faces the table; back to the viewer, feet under the table, chair back in front; drink or book in hand |
| fika.1 | fika-north.1 | Fika table, north | back | 04 | Faces the table; back to the viewer, feet under the table, chair back in front; drink or book in hand |
| fika.2 | fika-north.2 | Fika table, north | back | 04 | Faces the table; back to the viewer, feet under the table, chair back in front; drink or book in hand |
| fika.3 | fika-north.3 | Fika table, north | back | 04 | Faces the table; back to the viewer, feet under the table, chair back in front; drink or book in hand |
| fika.4 | fika-north.4 | Fika table, north | front | 04 | Faces the table; faces the viewer across the table, feet under the table; drink or book in hand |
| fika.5 | fika-north.5 | Fika table, north | front | 04 | Faces the table; faces the viewer across the table, feet under the table; drink or book in hand |
| fika.6 | fika-north.6 | Fika table, north | front | 04 | Faces the table; faces the viewer across the table, feet under the table; drink or book in hand |
| fika.7 | fika-north.7 | Fika table, north | front | 04 | Faces the table; faces the viewer across the table, feet under the table; drink or book in hand |
| fika.8 | fika-south.0 | Fika table, south | back | 04 | Faces the table; back to the viewer, feet under the table, chair back in front; drink or book in hand |
| fika.9 | fika-south.1 | Fika table, south | back | 04 | Faces the table; back to the viewer, feet under the table, chair back in front; drink or book in hand |
| fika.10 | fika-south.2 | Fika table, south | back | 04 | Faces the table; back to the viewer, feet under the table, chair back in front; drink or book in hand |
| fika.11 | fika-south.3 | Fika table, south | back | 04 | Faces the table; back to the viewer, feet under the table, chair back in front; drink or book in hand |
| fika.12 | fika-south.4 | Fika table, south | front | 04 | Faces the table; faces the viewer across the table, feet under the table; drink or book in hand |
| fika.13 | fika-south.5 | Fika table, south | front | 04 | Faces the table; faces the viewer across the table, feet under the table; drink or book in hand |
| fika.14 | fika-south.6 | Fika table, south | front | 04 | Faces the table; faces the viewer across the table, feet under the table; drink or book in hand |
| fika.15 | fika-south.7 | Fika table, south | front | 04 | Faces the table; faces the viewer across the table, feet under the table; drink or book in hand |
| fika.16 | sofa-north.0 | Sofa, north | front | 05 | Sits on the cushion facing the coffee table; feet on the floor in front of the sofa, not on the coffee table |
| fika.17 | sofa-north.1 | Sofa, north | front | 05 | Sits on the cushion facing the coffee table; feet on the floor in front of the sofa, not on the coffee table |
| fika.18 | sofa-north.2 | Sofa, north | front | 05 | Sits on the cushion facing the coffee table; feet on the floor in front of the sofa, not on the coffee table |
| fika.19 | sofa-south.0 | Sofa, south | back | 05 | Sits on the cushion facing the coffee table; seen from behind, sofa back in front of the lower body, head and shoulders not hidden by the coffee table |
| fika.20 | sofa-south.1 | Sofa, south | back | 05 | Sits on the cushion facing the coffee table; seen from behind, sofa back in front of the lower body, head and shoulders not hidden by the coffee table |
| fika.21 | sofa-south.2 | Sofa, south | back | 05 | Sits on the cushion facing the coffee table; seen from behind, sofa back in front of the lower body, head and shoulders not hidden by the coffee table |
| fika.22 | high-north.0 | High table, north | back | 05 | Sits on the stool facing the high table; feet on the stool rest or floor, no clipping through the table |
| fika.23 | high-north.1 | High table, north | side-left | 05 | Sits on the stool facing the high table; feet on the stool rest or floor, no clipping through the table |
| fika.24 | high-west.0 | High table, west | back | 05 | Sits on the stool facing the high table; feet on the stool rest or floor, no clipping through the table |
| fika.25 | high-west.1 | High table, west | side-left | 05 | Sits on the stool facing the high table; feet on the stool rest or floor, no clipping through the table; known overlap with fika.26 |
| fika.26 | high-east.0 | High table, east | back | 05 | Sits on the stool facing the high table; feet on the stool rest or floor, no clipping through the table; known overlap with fika.25 |
| fika.27 | high-east.1 | High table, east | side-left | 05 | Sits on the stool facing the high table; feet on the stool rest or floor, no clipping through the table |

## Recording the review

Record the owner's result per seat (accepted, or the defect seen) in the M2 Post-Closure Office Change section of the milestone record.
