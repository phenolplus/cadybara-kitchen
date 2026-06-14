import cadquery as cq

base = cq.Workplane("XY").box(32, 24, 5).translate((0, 0, 2.5))

outer_loop = cq.Workplane("YZ").circle(8).extrude(20).translate((-10, 0, 13))
inner_void = cq.Workplane("YZ").circle(4).extrude(24).translate((-12, 0, 13))
gap_cut = cq.Workplane("XY").box(8, 20, 20).translate((0, -8, 15))

mount_hole = cq.Workplane("XY").circle(2.4).extrude(8).translate((9, 0, -1))
counterbore = cq.Workplane("XY").circle(5.2).extrude(3).translate((9, 0, 3))

result = base.union(outer_loop).cut(inner_void).cut(gap_cut).cut(mount_hole).cut(counterbore)
