import cadquery as cq

height = 72
outer_radius = 36
wall = 3
bottom = 3
back_width = 78
back_height = 84
back_thickness = 4

outer = cq.Workplane("XY").circle(outer_radius).extrude(height)
inner_void = cq.Workplane("XY").workplane(offset=bottom).circle(outer_radius - wall).extrude(height + 2)
cup = outer.cut(inner_void)

back = (
    cq.Workplane("XY")
    .box(back_width, back_thickness, back_height)
    .translate((0, outer_radius + back_thickness / 2 - 0.5, back_height / 2 - 6))
)

mount_hole = cq.Workplane("XZ", origin=(0, outer_radius - 2, 58)).circle(3).extrude(12)

result = cup.union(back).cut(mount_hole)
