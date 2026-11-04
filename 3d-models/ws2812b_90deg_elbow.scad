// Parametric 90-degree elbow for ws2812b_modular_rail.scad.
// The centerline starts along +X, turns left, and exits along +Y.
// Set part to "rail", "cap", or "assembly" for the corresponding view/export.

part = "assembly";

// Requested route dimensions. The endpoint distance is measured between the
// centerline start and end, excluding the connector hooks.
entry_straight_length = 50;
target_endpoint_distance = 100;
bend_radius = 30;
bend_steps = 64;
cap_end_clearance = 2;
fill_led_channel = true;

// Keep these values in sync with ws2812b_modular_rail.scad.
led_width = 10;
led_height = 5;
led_side_clearance = 1;
base_thickness = 2;
wall_thickness = 2.6;
wall_height = 9.5;
print_clearance = 0.25;

hook_length = 5.5;
hook_beam_width = 1.2;
hook_beam_height = 1.0;
hook_position_z = 4.9;
hook_nose_length = 1.1;
socket_length = 6.2;
socket_throat_length = hook_length - hook_nose_length - 3 * print_clearance;

cap_thickness = 1.2;
cap_side_clearance = 0.25;
cap_skirt_thickness = 1.2;
cap_skirt_drop = 2.7;
cap_latch_depth = 0.5;
cap_latch_height = 0.8;

channel_width = led_width + 2 * led_side_clearance;
rail_width = channel_width + 2 * wall_thickness;
rail_height = base_thickness + wall_height;
cap_groove_z = rail_height - 2;
cap_groove_height = cap_latch_height + 0.4;
cap_latch_z = cap_groove_z + 0.2;
cap_top_width = rail_width + 2 * cap_side_clearance;
cap_skirt_center_offset = rail_width / 2 + cap_side_clearance
    + cap_skirt_thickness / 2;
cap_latch_center_offset = (
    rail_width / 2 - cap_latch_depth
    + rail_width / 2 + cap_side_clearance
) / 2;
cap_latch_width = cap_latch_depth + cap_side_clearance;
cap_print_latch_z = cap_thickness
    + rail_height - cap_latch_z - cap_latch_height;
hook_center_offset = channel_width / 2 + wall_thickness - hook_beam_width / 2;
epsilon = 0.02;

// Choose the remaining straight length so the route endpoint is exactly the
// requested Euclidean distance from the start.
exit_straight_length =
    sqrt(target_endpoint_distance * target_endpoint_distance
        - (entry_straight_length + bend_radius)
        * (entry_straight_length + bend_radius))
    - bend_radius;
bend_arc_length = PI * bend_radius / 2;
route_length = entry_straight_length + bend_arc_length + exit_straight_length;

function route_point_at(distance) =
    distance <= entry_straight_length
        ? [distance, 0]
        : distance <= entry_straight_length + bend_arc_length
            ? let (angle = (distance - entry_straight_length)
                    / bend_radius * 180 / PI)
                [entry_straight_length + bend_radius * sin(angle),
                 bend_radius * (1 - cos(angle))]
            : [entry_straight_length + bend_radius,
               bend_radius + distance - entry_straight_length - bend_arc_length];

// Include the straight-to-curve and curve-to-straight transitions exactly.
function route_points(trim = 0) = concat(
    [route_point_at(trim)],
    [for (i = [0:bend_steps])
        route_point_at(entry_straight_length + bend_arc_length * i / bend_steps)],
    [route_point_at(route_length - trim)]
);

module sweep_section(point, angle, width, lateral_offset, z, height) {
    normal_x = -sin(angle);
    normal_y = cos(angle);
    translate([
        point[0] + normal_x * lateral_offset,
        point[1] + normal_y * lateral_offset,
        z
    ])
        rotate([0, 0, angle])
            translate([-epsilon / 2, -width / 2, 0])
                cube([epsilon, width, height]);
}

// Approximate a swept rectangular strip with closely spaced hulls. The 64
// segments keep the quarter-circle smooth while preserving the rail profile.
module sweep_band(points, width, lateral_offset, z, height) {
    for (i = [0:len(points) - 2]) {
        start_point = points[i];
        end_point = points[i + 1];
        angle = atan2(
            end_point[1] - start_point[1],
            end_point[0] - start_point[0]
        );
        hull() {
            sweep_section(start_point, angle, width, lateral_offset, z, height);
            sweep_section(end_point, angle, width, lateral_offset, z, height);
        }
    }
}

module rail_channel(points) {
    difference() {
        union() {
            // Flat base and the two raised side walls.
            sweep_band(points, rail_width, 0, 0, base_thickness);
            for (side = [-1, 1])
                sweep_band(
                    points,
                    wall_thickness,
                    side * (channel_width / 2 + wall_thickness / 2),
                    base_thickness,
                    wall_height
                );
            // Optional solid fill; enabled for the exported elbow rail.
            if (fill_led_channel)
                sweep_band(
                    points,
                    channel_width + 2 * epsilon,
                    0,
                    base_thickness,
                    wall_height
                );
        }

        // Shallow external recesses for the elbow's press-on cap latches.
        for (side = [-1, 1])
            sweep_band(
                points,
                cap_latch_depth,
                side * (rail_width / 2 - cap_latch_depth / 2),
                cap_groove_z,
                cap_groove_height
            );
    }
}

module socket_cutouts_at(point, angle) {
    translate([point[0], point[1], 0])
        rotate([0, 0, angle])
            for (side = [-1, 1]) {
                socket_y = side * hook_center_offset;
                translate([
                    -epsilon,
                    socket_y - hook_beam_width / 2 - print_clearance,
                    hook_position_z - print_clearance
                ])
                    cube([
                        socket_throat_length + epsilon,
                        hook_beam_width + 2 * print_clearance,
                        hook_beam_height + 2 * print_clearance
                    ]);
                translate([
                    socket_throat_length,
                    socket_y - hook_beam_width / 2 - print_clearance,
                    hook_position_z - hook_beam_height
                ])
                    cube([
                        socket_length - socket_throat_length + epsilon,
                        hook_beam_width + 2 * print_clearance,
                        hook_beam_height * 3
                    ]);
            }
}

module hook_tabs_at(point, angle) {
    translate([point[0], point[1], 0])
        rotate([0, 0, angle])
            for (side = [-1, 1]) {
                hook_y = side * hook_center_offset - hook_beam_width / 2;
                union() {
                    translate([-epsilon, hook_y, hook_position_z])
                        cube([
                            hook_length + epsilon,
                            hook_beam_width,
                            hook_beam_height
                        ]);

                    hull() {
                        translate([
                            hook_length - hook_nose_length,
                            hook_y,
                            hook_position_z - hook_beam_height * 0.45
                        ])
                            cube([
                                epsilon,
                                hook_beam_width,
                                hook_beam_height * 1.9
                            ]);
                        translate([
                            hook_length - epsilon,
                            hook_y,
                            hook_position_z
                        ])
                            cube([
                                epsilon,
                                hook_beam_width,
                                hook_beam_height
                            ]);
                    }
                }
            }
}

module elbow_rail() {
    union() {
        difference() {
            rail_channel(route_points());
            // Entry sockets accept the hooks of a standard straight segment.
            socket_cutouts_at(route_point_at(0), 0);
        }
        // The outlet hooks are rotated to follow the +Y exit direction.
        hook_tabs_at(route_point_at(route_length), 90);
    }
}

module elbow_cap(assembled = false) {
    points = route_points(cap_end_clearance);
    top_z = assembled ? rail_height : 0;
    skirt_z = assembled
        ? rail_height - cap_skirt_drop
        : cap_thickness;
    latch_z = assembled ? cap_latch_z : cap_print_latch_z;
    union() {
        // Broad top plate and two skirts that press over the outside of the walls.
        sweep_band(points, cap_top_width, 0, top_z, cap_thickness);
        for (side = [-1, 1])
            sweep_band(
                points,
                cap_skirt_thickness,
                side * cap_skirt_center_offset,
                skirt_z,
                cap_skirt_drop
            );
        // The latch ribs engage the matching shallow recesses on the rail.
        for (side = [-1, 1])
            sweep_band(
                points,
                cap_latch_width,
                side * cap_latch_center_offset,
                latch_z,
                cap_latch_height
            );
    }
}

assert(bend_radius > 0, "bend_radius must be positive");
assert(bend_steps >= 16, "Use at least 16 steps for a smooth curve");
assert(target_endpoint_distance > entry_straight_length + bend_radius,
    "The endpoint distance is too short for this entry and bend radius");
assert(exit_straight_length >= cap_end_clearance,
    "The calculated exit straight must fit the cap end clearance");
assert(socket_throat_length > 0 && socket_throat_length < socket_length,
    "The hook throat must fit inside the receiving pocket");
assert(base_thickness + led_height < cap_groove_z,
    "The LED strip needs clearance inside the rail");
assert(cap_groove_z >= base_thickness
        && cap_groove_z + cap_groove_height <= rail_height,
    "The cap latches must remain inside the rail walls");

if (part == "rail") {
    elbow_rail();
} else if (part == "cap") {
    elbow_cap();
} else if (part == "assembly") {
    color("dimgray") elbow_rail();
    color([0.75, 0.88, 1, 0.75]) elbow_cap(assembled = true);
} else {
    assert(false, "part must be \"rail\", \"cap\", or \"assembly\"");
}
