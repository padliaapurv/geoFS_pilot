# Generates the JSBSim 777-200 aircraft XML from config/aircraft_b772.yaml,
# so the JSBSim model and our own Python aero model stay derived from the
# same single source of truth. Re-run this after editing the YAML.
#
# The aerodynamic build-up mirrors src/aircraft/aerodynamics.py exactly
# (same non-dimensional coefficients, same b/2V and c/2V rate reductions),
# just re-expressed as JSBSim <function> elements evaluated in wind axes
# (LIFT/DRAG/SIDE) and body axes (ROLL/PITCH/YAW), which JSBSim then
# composes using its own (quaternion-based, non-Euler) equations of motion.

import os
import yaml

M_TO_FT = 3.280839895
KG_TO_LB = 2.2046226218
KGM2_TO_SLUGFT2 = 23.730360404  # 1 kg*m^2 = 1 lb*ft*s^2-equivalent in slug*ft^2
N_TO_LBF = 0.2248089431

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)


def load_config():
    with open(os.path.join(REPO_ROOT, "config", "aircraft_b772.yaml")) as f:
        return yaml.safe_load(f)


def build_metrics(cfg):
    geom = cfg["geometry"]
    wing_area_ft2 = geom["wing_area_m2"] * M_TO_FT ** 2
    wing_span_ft = geom["wing_span_m"] * M_TO_FT
    chord_ft = geom["mean_aero_chord_m"] * M_TO_FT
    # Horizontal/vertical tail areas and arms aren't in our source config
    # (our aero model doesn't need them, it's a direct-coefficient model);
    # supply representative 777-200 values for JSBSim's metrics block, which
    # are used only for a couple of internal reference properties, not for
    # our own <function>-defined aerodynamics below.
    return f"""<metrics>
   <wingarea  unit="FT2"> {wing_area_ft2:.3f} </wingarea>
   <wingspan  unit="FT" > {wing_span_ft:.3f} </wingspan>
   <chord     unit="FT" > {chord_ft:.3f} </chord>
   <htailarea unit="FT2"> 730.0 </htailarea>
   <htailarm  unit="FT" > 88.0 </htailarm>
   <vtailarea unit="FT2"> 520.0 </vtailarea>
   <vtailarm  unit="FT" > 0 </vtailarm>
   <location name="AERORP" unit="IN"><x>0</x><y>0</y><z>0</z></location>
   <location name="EYEPOINT" unit="IN"><x>-1200</x><y>0</y><z>150</z></location>
   <location name="VRP" unit="IN"><x>0</x><y>0</y><z>0</z></location>
</metrics>"""


RESERVE_FUEL_LB = 5000.0  # small reserve so engines have fuel to draw from


def build_mass_balance(cfg):
    mass = cfg["mass"]
    # Total mass (emptywt + fuel) matches config's constant-mass cruise
    # assumption; the reserve fuel is small enough (~1%) that burn over a
    # ~30 min run barely dents total weight.
    empty_wt_lb = mass["mass_kg"] * KG_TO_LB - RESERVE_FUEL_LB
    inertia = mass["inertia_kg_m2"]
    ixx = inertia["Ixx"] * KGM2_TO_SLUGFT2
    iyy = inertia["Iyy"] * KGM2_TO_SLUGFT2
    izz = inertia["Izz"] * KGM2_TO_SLUGFT2
    ixz = inertia["Ixz"] * KGM2_TO_SLUGFT2
    # Entire mass modeled as emptywt at the CG; our source config has no
    # separate fuel/payload breakdown (constant-mass cruise assumption).
    return f"""<mass_balance>
   <ixx unit="SLUG*FT2"> {ixx:.1f} </ixx>
   <iyy unit="SLUG*FT2"> {iyy:.1f} </iyy>
   <izz unit="SLUG*FT2"> {izz:.1f} </izz>
   <ixy unit="SLUG*FT2"> 0 </ixy>
   <ixz unit="SLUG*FT2"> {ixz:.1f} </ixz>
   <iyz unit="SLUG*FT2"> 0 </iyz>
   <emptywt unit="LBS"> {empty_wt_lb:.1f} </emptywt>
   <location name="CG" unit="IN"><x>0</x><y>0</y><z>0</z></location>
</mass_balance>"""


GROUND_REACTIONS = """<ground_reactions>
  <contact type="BOGEY" name="NOSE_GEAR">
    <location unit="IN"><x>-950</x><y>0</y><z>-170</z></location>
    <static_friction>0.40</static_friction>
    <dynamic_friction>0.30</dynamic_friction>
    <rolling_friction>0.02</rolling_friction>
    <spring_coeff unit="LBS/FT">200000</spring_coeff>
    <damping_coeff unit="LBS/FT/SEC">100000</damping_coeff>
    <max_steer unit="DEG">70</max_steer>
    <brake_group>NONE</brake_group>
    <retractable>1</retractable>
  </contact>
  <contact type="BOGEY" name="LEFT_MAIN">
    <location unit="IN"><x>100</x><y>-200</y><z>-180</z></location>
    <static_friction>0.40</static_friction>
    <dynamic_friction>0.35</dynamic_friction>
    <rolling_friction>0.02</rolling_friction>
    <spring_coeff unit="LBS/FT">1000000</spring_coeff>
    <damping_coeff unit="LBS/FT/SEC">200000</damping_coeff>
    <max_steer unit="DEG">0</max_steer>
    <brake_group>LEFT</brake_group>
    <retractable>1</retractable>
  </contact>
  <contact type="BOGEY" name="RIGHT_MAIN">
    <location unit="IN"><x>100</x><y>200</y><z>-180</z></location>
    <static_friction>0.40</static_friction>
    <dynamic_friction>0.35</dynamic_friction>
    <rolling_friction>0.02</rolling_friction>
    <spring_coeff unit="LBS/FT">1000000</spring_coeff>
    <damping_coeff unit="LBS/FT/SEC">200000</damping_coeff>
    <max_steer unit="DEG">0</max_steer>
    <brake_group>RIGHT</brake_group>
    <retractable>1</retractable>
  </contact>
</ground_reactions>"""


def build_propulsion(cfg):
    geom = cfg["geometry"]
    half_span_ft = geom["wing_span_m"] * M_TO_FT / 2.0
    engine_y_ft = half_span_ft * 0.35  # representative underwing mount, inboard of the tip
    return f"""<propulsion>
  <engine file="GE90-94B">
    <feed>0</feed>
    <thruster file="direct">
      <location unit="IN"><x>1200</x><y>{-engine_y_ft * 12:.1f}</y><z>-60</z></location>
      <orient unit="DEG"><pitch>0</pitch><roll>0</roll><yaw>0</yaw></orient>
    </thruster>
  </engine>
  <engine file="GE90-94B">
    <feed>0</feed>
    <thruster file="direct">
      <location unit="IN"><x>1200</x><y>{engine_y_ft * 12:.1f}</y><z>-60</z></location>
      <orient unit="DEG"><pitch>0</pitch><roll>0</roll><yaw>0</yaw></orient>
    </thruster>
  </engine>
  <tank type="FUEL" number="0">
    <location unit="IN"><x>0</x><y>0</y><z>0</z></location>
    <capacity unit="LBS">320000</capacity>
    <contents unit="LBS">{RESERVE_FUEL_LB}</contents>
  </tank>
</propulsion>"""


def build_flight_control(cfg):
    surf = cfg["control_surfaces"]

    def surface_channel(name, cmd_prop, pos_rad_prop, pos_norm_prop, limit_rad, rate_limit_rad_s, time_constant_s):
        # Normalized rate limit and lag, since the actuator here operates on
        # the -1..1 normalized command before the aerosurface_scale expands
        # it to +-limit_rad -- mirrors control_surfaces.ActuatorModel exactly
        # (first-order lag + rate limit + position limit), just running
        # inside JSBSim instead of our own Python actuator model.
        normalized_rate_limit = rate_limit_rad_s / limit_rad
        lag_time_constant = time_constant_s
        return f"""  <channel name="{name}">
    <actuator name="{name} Actuator">
      <input>{cmd_prop}</input>
      <lag>{1.0 / lag_time_constant:.4f}</lag>
      <rate_limit>{normalized_rate_limit:.4f}</rate_limit>
      <clipto><min>-1</min><max>1</max></clipto>
      <output>{pos_norm_prop}</output>
    </actuator>
    <aerosurface_scale name="{name} to rad">
      <input>{pos_norm_prop}</input>
      <range><min>{-limit_rad:.5f}</min><max>{limit_rad:.5f}</max></range>
      <output>{pos_rad_prop}</output>
    </aerosurface_scale>
  </channel>"""

    aileron = surface_channel(
        "Aileron", "fcs/aileron-cmd-norm", "fcs/aileron-pos-rad", "fcs/aileron-pos-norm",
        surf["aileron"]["limit_rad"], surf["aileron"]["rate_limit_rad_s"], surf["aileron"]["time_constant_s"],
    )
    elevator = surface_channel(
        "Elevator", "fcs/elevator-cmd-norm", "fcs/elevator-pos-rad", "fcs/elevator-pos-norm",
        surf["elevator"]["limit_rad"], surf["elevator"]["rate_limit_rad_s"], surf["elevator"]["time_constant_s"],
    )
    rudder = surface_channel(
        "Rudder", "fcs/rudder-cmd-norm", "fcs/rudder-pos-rad", "fcs/rudder-pos-norm",
        surf["rudder"]["limit_rad"], surf["rudder"]["rate_limit_rad_s"], surf["rudder"]["time_constant_s"],
    )
    elevator_trim = surface_channel(
        "ElevatorTrim", "fcs/pitch-trim-cmd-norm", "fcs/pitch-trim-pos-rad", "fcs/pitch-trim-pos-norm",
        surf["elevator_trim"]["limit_rad"], surf["elevator_trim"]["rate_limit_rad_s"], surf["elevator_trim"]["time_constant_s"],
    )

    throttle_rate = surf["throttle"]["rate_limit_fraction_s"]
    throttle = f"""  <channel name="Throttle">
    <actuator name="Throttle Actuator 0">
      <input>fcs/throttle-cmd-norm</input>
      <lag>{1.0 / surf["throttle"]["time_constant_s"]:.4f}</lag>
      <rate_limit>{throttle_rate:.4f}</rate_limit>
      <clipto><min>0</min><max>1</max></clipto>
      <output>fcs/throttle-pos-norm</output>
    </actuator>
    <actuator name="Throttle Actuator 1">
      <input>fcs/throttle-cmd-norm[1]</input>
      <lag>{1.0 / surf["throttle"]["time_constant_s"]:.4f}</lag>
      <rate_limit>{throttle_rate:.4f}</rate_limit>
      <clipto><min>0</min><max>1</max></clipto>
      <output>fcs/throttle-pos-norm[1]</output>
    </actuator>
  </channel>"""

    return f"""<flight_control name="FCS: 777-200">
  <property value="0">fcs/pitch-trim-cmd-norm</property>
{aileron}
{elevator}
{elevator_trim}
{rudder}
{throttle}
</flight_control>"""


def build_aerodynamics(cfg):
    aero = cfg["aerodynamics"]
    lift = aero["lift"]
    drag = aero["drag"]
    pitch = aero["pitch_moment"]
    side = aero["side_force"]
    roll = aero["roll_moment"]
    yaw = aero["yaw_moment"]
    geom = cfg["geometry"]
    aspect_ratio = geom["wing_span_m"] ** 2 / geom["wing_area_m2"]
    induced_drag_k = 1.0 / (3.14159265 * drag["oswald_efficiency"] * aspect_ratio)

    # aero/ci2vel = cbar / (2V), aero/bi2vel = b / (2V): JSBSim's built-in
    # rate-reduction properties, matching our c2v/b2v exactly.
    return f"""<aerodynamics>

  <axis name="LIFT">
    <function name="aero/force/Lift_basic">
      <description>CL0 + CL_alpha*alpha</description>
      <product>
        <property>aero/qbar-psf</property>
        <property>metrics/Sw-sqft</property>
        <sum>
          <value>{lift["CL0"]}</value>
          <product><value>{lift["CL_alpha"]}</value><property>aero/alpha-rad</property></product>
        </sum>
      </product>
    </function>
    <function name="aero/force/Lift_elevator">
      <product>
        <property>aero/qbar-psf</property>
        <property>metrics/Sw-sqft</property>
        <value>{lift["CL_elevator"]}</value>
        <property>fcs/elevator-pos-rad</property>
      </product>
    </function>
    <function name="aero/force/Lift_elevator_trim">
      <product>
        <property>aero/qbar-psf</property>
        <property>metrics/Sw-sqft</property>
        <value>{lift["CL_elevator_trim"]}</value>
        <property>fcs/pitch-trim-pos-rad</property>
      </product>
    </function>
    <function name="aero/force/Lift_q">
      <product>
        <property>aero/qbar-psf</property>
        <property>metrics/Sw-sqft</property>
        <value>{lift["CL_q"]}</value>
        <property>aero/ci2vel</property>
        <property>velocities/q-aero-rad_sec</property>
      </product>
    </function>
  </axis>

  <axis name="DRAG">
    <function name="aero/force/Drag_basic">
      <description>CD0 + k*CL^2</description>
      <product>
        <property>aero/qbar-psf</property>
        <property>metrics/Sw-sqft</property>
        <sum>
          <value>{drag["CD0"]}</value>
          <product><value>{induced_drag_k}</value><property>aero/cl-squared</property></product>
        </sum>
      </product>
    </function>
  </axis>

  <axis name="SIDE">
    <function name="aero/force/Side_beta">
      <product>
        <property>aero/qbar-psf</property>
        <property>metrics/Sw-sqft</property>
        <value>{side["CY_beta"]}</value>
        <property>aero/beta-rad</property>
      </product>
    </function>
    <function name="aero/force/Side_rudder">
      <product>
        <property>aero/qbar-psf</property>
        <property>metrics/Sw-sqft</property>
        <value>{side["CY_rudder"]}</value>
        <property>fcs/rudder-pos-rad</property>
      </product>
    </function>
  </axis>

  <axis name="ROLL">
    <function name="aero/moment/Roll_beta">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{roll["Cl_beta"]}</value><property>aero/beta-rad</property>
      </product>
    </function>
    <function name="aero/moment/Roll_p">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{roll["Cl_p"]}</value><property>aero/bi2vel</property><property>velocities/p-aero-rad_sec</property>
      </product>
    </function>
    <function name="aero/moment/Roll_r">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{roll["Cl_r"]}</value><property>aero/bi2vel</property><property>velocities/r-aero-rad_sec</property>
      </product>
    </function>
    <function name="aero/moment/Roll_aileron">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{roll["Cl_aileron"]}</value><property>fcs/aileron-pos-rad</property>
      </product>
    </function>
    <function name="aero/moment/Roll_rudder">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{roll["Cl_rudder"]}</value><property>fcs/rudder-pos-rad</property>
      </product>
    </function>
  </axis>

  <axis name="PITCH">
    <function name="aero/moment/Pitch_basic">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/cbarw-ft</property>
        <sum>
          <value>{pitch["Cm0"]}</value>
          <product><value>{pitch["Cm_alpha"]}</value><property>aero/alpha-rad</property></product>
        </sum>
      </product>
    </function>
    <function name="aero/moment/Pitch_elevator">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/cbarw-ft</property>
        <value>{pitch["Cm_elevator"]}</value><property>fcs/elevator-pos-rad</property>
      </product>
    </function>
    <function name="aero/moment/Pitch_elevator_trim">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/cbarw-ft</property>
        <value>{pitch["Cm_elevator_trim"]}</value><property>fcs/pitch-trim-pos-rad</property>
      </product>
    </function>
    <function name="aero/moment/Pitch_q">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/cbarw-ft</property>
        <value>{pitch["Cm_q"]}</value><property>aero/ci2vel</property><property>velocities/q-aero-rad_sec</property>
      </product>
    </function>
  </axis>

  <axis name="YAW">
    <function name="aero/moment/Yaw_beta">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{yaw["Cn_beta"]}</value><property>aero/beta-rad</property>
      </product>
    </function>
    <function name="aero/moment/Yaw_p">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{yaw["Cn_p"]}</value><property>aero/bi2vel</property><property>velocities/p-aero-rad_sec</property>
      </product>
    </function>
    <function name="aero/moment/Yaw_r">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{yaw["Cn_r"]}</value><property>aero/bi2vel</property><property>velocities/r-aero-rad_sec</property>
      </product>
    </function>
    <function name="aero/moment/Yaw_aileron">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{yaw["Cn_aileron"]}</value><property>fcs/aileron-pos-rad</property>
      </product>
    </function>
    <function name="aero/moment/Yaw_rudder">
      <product>
        <property>aero/qbar-psf</property><property>metrics/Sw-sqft</property><property>metrics/bw-ft</property>
        <value>{yaw["Cn_rudder"]}</value><property>fcs/rudder-pos-rad</property>
      </product>
    </function>
  </axis>

</aerodynamics>"""


def generate():
    cfg = load_config()
    xml = f"""<?xml version="1.0"?>
<?xml-stylesheet type="text/xsl" href="http://jsbsim.sourceforge.net/JSBSim.xsl"?>
<fdm_config name="777-200" version="2.0" release="ALPHA"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:noNamespaceSchemaLocation="http://jsbsim.sourceforge.net/JSBSim.xsd">

<fileheader>
  <author>Generated by scripts/generate_jsbsim_aircraft.py</author>
  <description>Boeing 777-200 cruise model, coefficients sourced from config/aircraft_b772.yaml (see that file's header for data provenance/caveats). GENERATED FILE -- edit the YAML and regenerate, do not hand-edit.</description>
</fileheader>

{build_metrics(cfg)}

{build_mass_balance(cfg)}

{GROUND_REACTIONS}

{build_propulsion(cfg)}

{build_flight_control(cfg)}

{build_aerodynamics(cfg)}

</fdm_config>
"""
    out_dir = os.path.join(REPO_ROOT, "jsbsim_models", "aircraft", "777-200")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "777-200.xml")
    with open(out_path, "w") as f:
        f.write(xml)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    generate()
