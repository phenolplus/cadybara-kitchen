import cadquery as cq

height = 90
outer_radius = 40
wall = 3
bottom = 3
back_width = 90
back_height = 100
back_thickness = 4
panel_center_z = 45
panel_center_y = outer_radius + back_thickness / 2 - 0.8

outer = cq.Workplane("XY").circle(outer_radius).extrude(height)
inner_void = cq.Workplane("XY").workplane(offset=bottom).circle(outer_radius - wall).extrude(height + 3)
body = outer.cut(inner_void)

back_panel = (
    cq.Workplane("XY")
    .box(back_width, back_thickness, back_height)
    .translate((0, panel_center_y, panel_center_z))
)

result = body.union(back_panel)

for x in (-15, 15):
    for y in (-15, 15):
        drain = cq.Workplane("XY").workplane(offset=-1).center(x, y).circle(1.5).extrude(bottom + 2)
        result = result.cut(drain)

slot_center_z = 71
circle_center_z = 76
keyhole_circle = cq.Workplane("XZ", origin=(0, outer_radius - 2, circle_center_z)).circle(4).extrude(12)
keyhole_slot = cq.Workplane("XZ", origin=(0, outer_radius - 2, slot_center_z)).rect(4, 10).extrude(12)

result = result.cut(keyhole_circle).cut(keyhole_slot)
