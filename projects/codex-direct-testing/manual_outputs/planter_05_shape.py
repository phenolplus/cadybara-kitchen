import cadquery as cq

height = 86
outer_radius = 40
wall = 3
bottom = 3
back_width = 88
back_height = 96
back_thickness = 4

outer = cq.Workplane("XY").circle(outer_radius).extrude(height)
inner_void = cq.Workplane("XY").workplane(offset=bottom).circle(outer_radius - wall).extrude(height + 3)
cup = outer.cut(inner_void)

flat_back = (
    cq.Workplane("XY")
    .box(back_width, back_thickness, back_height)
    .translate((0, outer_radius + back_thickness / 2 - 0.8, back_height / 2 - 5))
)

screw_hole = cq.Workplane("XZ", origin=(0, outer_radius - 2, 68)).circle(3.2).extrude(12)
countersink = cq.Workplane("XZ", origin=(0, outer_radius + 1, 68)).circle(5.6).extrude(5)

result = cup.union(flat_back).cut(screw_hole).cut(countersink)
