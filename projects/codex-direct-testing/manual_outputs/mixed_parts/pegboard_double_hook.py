import cadquery as cq

back_plate = cq.Workplane("XY").box(54, 5, 70).translate((0, 0, 35))

peg_top = cq.Workplane("YZ").circle(3).extrude(18).translate((-16, -11, 50))
peg_bottom = cq.Workplane("YZ").circle(3).extrude(18).translate((16, -11, 24))

hook_left_bar = cq.Workplane("YZ").circle(3.2).extrude(48).translate((-14, 8, 30))
hook_left_tip = cq.Workplane("XY").box(8, 8, 18).translate((-38, 8, 38))
hook_right_bar = cq.Workplane("YZ").circle(3.2).extrude(48).translate((14, 8, 30))
hook_right_tip = cq.Workplane("XY").box(8, 8, 18).translate((38, 8, 38))

brace_left = cq.Workplane("XY").box(32, 5, 5).translate((-24, 6, 25)).rotate((0, 0, 25), (0, 1, 25), 28)
brace_right = cq.Workplane("XY").box(32, 5, 5).translate((24, 6, 25)).rotate((0, 0, 25), (0, 1, 25), -28)

result = (
    back_plate.union(peg_top)
    .union(peg_bottom)
    .union(hook_left_bar)
    .union(hook_left_tip)
    .union(hook_right_bar)
    .union(hook_right_tip)
    .union(brace_left)
    .union(brace_right)
)
