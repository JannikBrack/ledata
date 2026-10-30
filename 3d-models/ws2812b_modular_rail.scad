// Modular WS2812B rail for Bambu Lab P1 printers.
// Set segment_length to 200 for a standard section or 100 for a short section.

segment_length = 200;

led_width = 10;
led_height = 5;
led_side_clearance = 1;
base_thickness = 2;
wall_thickness = 2.6;
wall_height = 9.5;
roof_slot_height = 1.5;
roof_slot_bottom = 8;
roof_slot_depth = 1.5;
print_clearance = 0.25;

hook_length = 5.5;
hook_beam_width = 1.2;
hook_beam_height = 1.0;
hook_position_z = 4.9;
hook_nose_length = 1.1;
socket_length = 6.2;
socket_throat_length = hook_length - hook_nose_length - 3 * print_clearance;

channel_width = led_width + 2 * led_side_clearance;
rail_width = channel_width + 2 * wall_thickness;
rail_height = base_thickness + wall_height;
groove_depth = roof_slot_depth + print_clearance;
epsilon = 0.02;

module rail_cross_section() {
    difference() {
        union() {
            translate([0, -rail_width / 2])
                square([base_thickness, rail_width]);
            translate([base_thickness, -rail_width / 2])
                square([wall_height, wall_thickness]);
            translate([base_thickness, channel_width / 2])
                square([wall_height, wall_thickness]);
        }

        translate([
            roof_slot_bottom,
            -channel_width / 2 - groove_depth
        ])
            square([roof_slot_height, groove_depth + epsilon]);
        translate([
            roof_slot_bottom,
            channel_width / 2 - epsilon
        ])
            square([roof_slot_height, groove_depth + epsilon]);
    }
}

module rail_body() {
    difference() {
        translate([segment_length, 0, 0])
            rotate([0, -90, 0])
                linear_extrude(height = segment_length)
                    rail_cross_section();

        // The socket has a narrow entry throat and a wider catch pocket.
        for (side = [-1, 1]) {
            socket_center_y = side * (
                channel_width / 2 + wall_thickness - hook_beam_width / 2
            );
            translate([
                -epsilon,
                socket_center_y - hook_beam_width / 2 - print_clearance,
                hook_position_z - print_clearance
            ])
                cube([
                    socket_throat_length + epsilon,
                    hook_beam_width + 2 * print_clearance,
                    hook_beam_height + 2 * print_clearance
                ]);
            translate([
                socket_throat_length,
                socket_center_y - hook_beam_width / 2 - print_clearance,
                hook_position_z - hook_beam_height
            ])
                cube([
                    socket_length - socket_throat_length + epsilon,
                    hook_beam_width + 2 * print_clearance,
                    hook_beam_height * 3
                ]);
        }
    }
}

module hook_tab(side) {
    tab_center_y = side * (
        channel_width / 2 + wall_thickness - hook_beam_width / 2
    );
    union() {
        translate([
            segment_length - epsilon,
            tab_center_y - hook_beam_width / 2,
            hook_position_z
        ])
            cube([hook_length + epsilon, hook_beam_width, hook_beam_height]);

        hull() {
            translate([
                segment_length + hook_length - hook_nose_length,
                tab_center_y - hook_beam_width / 2,
                hook_position_z - hook_beam_height * 0.45
            ])
                cube([
                    epsilon,
                    hook_beam_width,
                    hook_beam_height * 1.9
                ]);
            translate([
                segment_length + hook_length - epsilon,
                tab_center_y - hook_beam_width / 2,
                hook_position_z
            ])
                cube([epsilon, hook_beam_width, hook_beam_height]);
        }
    }
}

assert(segment_length >= socket_length && segment_length + hook_length <= 256,
    "segment_length must fit the socket and the Bambu Lab P1 build plate");
assert(socket_throat_length > 0 && socket_throat_length < socket_length,
    "The hook throat must fit inside the receiving pocket");
assert(roof_slot_bottom + roof_slot_height <= rail_height,
    "The roof groove must remain inside the rail wall");
assert(base_thickness + led_height < roof_slot_bottom,
    "The LED strip needs clearance below the roof");
assert(wall_thickness > groove_depth,
    "The rail needs a wall behind the roof groove");
assert(rail_width <= 256,
    "The rail must fit within the Bambu Lab P1 build plate");

union() {
    rail_body();
    for (side = [-1, 1])
        hook_tab(side);
}
