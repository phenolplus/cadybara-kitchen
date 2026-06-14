import cadquery as cq

height = 78
outer_radius = 38
wall = 3
bottom = 3
back_width = 84
back_height = 92
back_thickness = 4

outer = cq.Workplane("XY").circle(outer_radius).extrude(height)
inner_void = cq.Workplane("XY").workplane(offset=bottom).circle(outer_radius - wall).extrude(height + 3)
cup = outer.cut(inner_void)

back = (
    cq.Workplane("XY")
    .box(back_width, back_thickness, back_height)
    .translate((0, outer_radius + back_thickness / 2 - 0.7, back_height / 2 - 7))
)

screw_clearance = cq.Workplane("XZ", origin=(0, outer_radius - 2, 64)).circle(3.2).extrude(12)
head_pocket = cq.Workplane("XZ", origin=(0, outer_radius + 1, 64)).circle(5.5).extrude(5)

result = cup.union(back).cut(screw_clearance).cut(head_pocket)
