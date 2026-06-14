import cadquery as cq

vertical = cq.Workplane("XY").box(8, 76, 96).translate((-34, 0, 48))
horizontal = cq.Workplane("XY").box(86, 76, 8).translate((5, 0, 4))

rib_profile = cq.Workplane("XZ").polyline([(0, 0), (58, 0), (0, 62)]).close().extrude(6)
rib_a = rib_profile.translate((-30, -23, 8))
rib_b = rib_profile.translate((-30, 0, 8))
rib_c = rib_profile.translate((-30, 23, 8))

result = vertical.union(horizontal).union(rib_a).union(rib_b).union(rib_c)

for y in (-22, 22):
    wall_hole = cq.Workplane("YZ", origin=(-39, y, 54)).circle(3.2).extrude(12)
    result = result.cut(wall_hole)

for y in (-22, 22):
    shelf_hole = cq.Workplane("XY", origin=(12, y, 0)).circle(3.2).extrude(14)
    result = result.cut(shelf_hole)
