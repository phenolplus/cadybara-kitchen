import cadquery as cq

base_left = cq.Workplane("XY").circle(9).extrude(8).translate((-32, 0, 0))
base_right = cq.Workplane("XY").circle(9).extrude(8).translate((32, 0, 0))

grip = cq.Workplane("YZ").circle(5).extrude(64).translate((-32, 0, 20))
grip = grip.rotate((0, 0, 20), (1, 0, 20), 0)

left_riser = cq.Workplane("XY").box(12, 12, 22).translate((-32, 0, 11))
right_riser = cq.Workplane("XY").box(12, 12, 22).translate((32, 0, 11))

left_hole = cq.Workplane("XY").circle(2.3).extrude(12).translate((-32, 0, -2))
right_hole = cq.Workplane("XY").circle(2.3).extrude(12).translate((32, 0, -2))

result = base_left.union(base_right).union(left_riser).union(right_riser).union(grip)
result = result.cut(left_hole).cut(right_hole)
