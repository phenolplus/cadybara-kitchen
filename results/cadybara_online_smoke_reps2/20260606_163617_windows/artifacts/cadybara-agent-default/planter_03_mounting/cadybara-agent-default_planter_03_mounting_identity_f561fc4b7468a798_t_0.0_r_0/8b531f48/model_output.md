import cadquery as cq

# @group Overall Dimensions
height = 110.0      # @param min=50 max=300 unit=mm
total_width = 120.0 # @param min=50 max=300 unit=mm
total_depth = 100.0 # @param min=50 max=300 unit=mm

# @group Pot Cavity
pot_dia_top = 90.0  # @param min=40 max=200 unit=mm
pot_dia_bot = 80.0  # @param min=40 max=200 unit=mm
pot_depth = 95.0    # @param min=30 max=250 unit=mm
wall_min = 4.0      # @param min=2 max=10 unit=mm

# @group Keyhole Slot
entry_dia = 9.0     # @param min=5 max=15 unit=mm
neck_width = 4.5    # @param min=2 max=10 unit=mm
recess_depth = 6.0  # @param min=2 max=12 unit=mm
keyhole_len = 12.0  # @param min=5 max=30 unit=mm

def build_planter():
    # 1. Create the base hexagonal body
    # We want a flat back face. A regular hexagon has points. 
    # We will orient the hexagon so a flat side is against the wall (YZ plane).
    # Since total_width is vertex-to-vertex, circumscribed diameter = total_width.
    
    # We use a loft to create the "faceted bowl" look or just extrude and taper?
    # Design says "truncated hexagonal pyramid". Let's loft from a smaller base to top.
    bot_scale = 0.8
    
    body = (
        cq.Workplane("XY")
        .polygon(6, total_width * bot_scale)
        .workplane(offset=height)
        .polygon(6, total_width)
        .loft(combine=True)
    )
    
    # 2. Slice the back to make it flat for wall mounting
    # The hexagon is centered. Let's move it so the back face is at Y = 0.
    # The apothem of the top hexagon is (total_width/2) * cos(30 deg)
    apothem = (total_width / 2.0) * 0.866
    
    # Translate the body so the back-most point (or edge) is at Y=0
    # Currently center is 0,0. Back edge at -apothem.
    body = body.translate((0, apothem, 0))
    
    # Cut the back face to ensure it's perfectly flat against Y=0
    body = body.cut(
        cq.Workplane("XZ")
        .workplane(offset=-10) # slightly behind the wall plane
        .box(total_width * 2, 20, height * 2, centered=(True, False, True))
    )
    
    # 3. Internal Cavity (Tapered Cylinder)
    # The cavity should be centered relative to the body's mass or slightly shifted?
    # Let's center it in the top face's area.
    # Top surface is at Z=height.
    cavity = (
        cq.Workplane("XY")
        .workplane(offset=height - pot_depth)
        .circle(pot_dia_bot / 2.0)
        .workplane(offset=pot_depth + 1) # extend slightly above for clean cut
        .circle(pot_dia_top / 2.0)
        .loft(combine=False)
    )
    
    # Position cavity: centered in X, but offset from the flat back in Y
    # Ensure minimum wall thickness at the back. 
    # Back is at Y=0. Cavity center should be at Y = wall_min + pot_dia_top/2
    cavity_y_offset = apothem # Center of the original hexagon
    body = body.cut(cavity.translate((0, cavity_y_offset, 0)))

    # 4. Keyhole Slot on the flat back (Y=0 plane, looking in +Y direction)
    # The entry hole is at the bottom of the slot.
    keyhole_z = height * 0.75 # Position near top
    
    # Slot entry (large hole)
    # Slot neck (narrow part above)
    # Recess (space for the screw head behind the face)
    
    # We use a sketch-like approach on the XZ plane at Y=0
    # First, the deep recess for the screw head
    keyhole_recess = (
        cq.Workplane("XZ")
        .workplane(offset=0) # At the wall surface
        .move(0, keyhole_z)
        .slot2D(keyhole_len + entry_dia, entry_dia, angle=90)
        .extrude(recess_depth)
    )
    
    # Second, the narrow neck slot that the screw slides into
    keyhole_neck = (
        cq.Workplane("XZ")
        .workplane(offset=-1) # Start slightly outside to ensure clean cut
        .move(0, keyhole_z)
        .slot2D(keyhole_len + neck_width, neck_width, angle=90)
        .extrude(recess_depth + 2)
    )
    
    # Combine cuts
    body = body.cut(keyhole_recess).cut(keyhole_neck)

    # 5. Finishing touches: Top rim chamfer
    # Select the top edges.
    top_edges = body.edges(">Z")
    body = top_edges.chamfer(1.0)
    
    return body

result = build_planter()
