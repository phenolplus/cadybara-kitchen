import cadquery as cq

height = 90
outer_radius = 40
wall = 3
bottom = 3
back_width = 90
back_height = 100
back_thickness = 4

outer = cq.Workplane("XY").circle(outer_radius).extrude(height)
inner_void = cq.Workplane("XY").workplane(offset=bottom).circle(outer_radius - wall).extrude(height + 3)
cup = outer.cut(inner_void)

back_panel = (
    cq.Workplane("XY")
    .box(back_width, back_thickness, back_height)
    .translate((0, outer_radius + back_thickness / 2 - 0.8, back_height / 2 - 5))
)

number_8_clearance = cq.Workplane("XZ", origin=(0, outer_radius - 2, 72)).circle(2.5).extrude(12)
head_relief = cq.Workplane("XZ", origin=(0, outer_radius + 1, 72)).circle(4.8).extrude(5)

result = cup.union(back_panel).cut(number_8_clearance).cut(head_relief)
