import cadquery as cq
import planter_body
import wall_bracket

# @group Dimensions
width = 150.0  # @param min=100 max=300 unit=mm
height = 140.0 # @param min=80 max=250 unit=mm
depth = 120.0  # @param min=60 max=200 unit=mm
wall_thickness = 3.0 # @param min=2 max=5 unit=mm

# @group Features
reservoir_height = 15.0 # @param min=10 max=40 unit=mm
drain_hole_dia = 4.0    # @param min=2 max=8 unit=mm

# @group Mounting
bracket_width = 60.0    # @param min=30 max=100 unit=mm
bracket_height = 40.0   # @param min=20 max=80 unit=mm
bracket_thickness = 6.0 # @param min=4 max=10 unit=mm

def main():
    # Build Parts
    body = planter_body.build(
        width, height, depth, 
        wall_thickness, reservoir_height, 
        drain_hole_dia, 
        bracket_width, bracket_height, bracket_thickness
    )
    
    bracket = wall_bracket.build(
        bracket_width, bracket_height, bracket_thickness,
        hole_spacing = bracket_height * 0.6
    )
    
    # Assembly
    assy = cq.Assembly()
    
    # The bracket is fixed to the wall
    # Back face of bracket is at Y=0
    assy.add(bracket, name="bracket")
    
    # The planter body slides onto the bracket.
    # The slot in the body was at Z = height-10.
    # The bracket in wall_bracket.py was built from World Z=0 downwards.
    # Position the body so the bracket fits in the slot.
    body_offset_z = -(height - 10)
    
    assy.add(body, name="planter", loc=cq.Location(cq.Vector(0, 0, body_offset_z)))
    
    return assy

result = main()
