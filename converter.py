import pandapower.converter as pc
import pandapower as pp
import pandas as pd
import numpy as np
import mat73
import json
import copy
import os

from pandapower.converter.matpower.from_mpc import _adjust_ppc_indices, _change_ppc_TAP_value
from pandapower.converter.matpower.to_mpc import _ppc2mpc

MATPOWER_DIR = "matpower"
NAMES_DIR = "names"
SHUNTS_DIR = "shunts"


def from_mpc(file_path):
    """Implementation of from_mpc that supports both .m and .mat files, while allowing matlab 7.3 .m format."""

    def from_m(file_path):
        from pandapower.converter.matpower.from_mpc import _m2ppc, from_ppc
        ppc = _m2ppc(file_path, "mpc")
        mask = ppc["bus"][:, 1] == 1
        ppc["bus"][mask, 1] = 2
        ppc["bus"][:, 11] = 1.1
        ppc["bus"][:, 12] = 0.9
        return from_ppc(ppc)

    def load_object_names(power_grid, file_path):
        try:
            power_grid_name = os.path.splitext(os.path.basename(file_path))[0]
            names_dir = os.path.join(os.path.dirname(os.path.dirname(file_path)), NAMES_DIR)
            name_path = os.path.join(names_dir, power_grid_name+".json")
            with open(name_path, 'r') as f:
                name_dict = json.load(f)
            for key, name_list in name_dict.items():
                power_grid.get(key).name = name_list
        except:
            pass

    def load_shunts(power_grid, file_path):
        power_grid_name = os.path.splitext(os.path.basename(file_path))[0]
        shunts_dir = os.path.join(os.path.dirname(os.path.dirname(file_path)), SHUNTS_DIR)
        shunt_path = os.path.join(shunts_dir, power_grid_name+".csv")
        shunts = pd.read_csv(shunt_path)
        shunts.rename(columns={'Bs': 'q_mvar', 'Gs': 'p_mw', 'status': 'in_service'}, inplace=True)
        shunts["q_mvar"] = - shunts["q_mvar"]  # Bs = - Q
        shunts["step"] = 0.
        for i, shunt in shunts.iterrows():
            bus_id = shunt['bus']
            if bus_id in power_grid.shunt.bus.values:
                q_mvar = power_grid.shunt.q_mvar[power_grid.shunt.bus == bus_id]
                step = q_mvar / shunt.q_mvar
                shunts["step"].iloc[i] = step

        shunts["name"] = "0"
        power_grid.shunt = shunts

    power_grid = from_m(file_path)
    load_shunts(power_grid, file_path)
    load_object_names(power_grid, file_path)
    power_grid.name = os.path.splitext(os.path.basename(file_path))[0]
    return power_grid


def to_mpc(net, path, **kwargs):
    """Modification of the `to_mpc` implementation of pandapower
    (https://github.com/e2nIEE/pandapower/blob/develop/pandapower/converter/matpower/to_mpc.py)

    The present implementation saves all objects and sets the status of out-of-service
    objects to 0.
    The default implementation deletes objects that are out-of-service, which
    completely alters the object ordering. For visualization purpose, panoramix relies
    heavily on this ordering.
    """

    # Create default directories containing the different components
    matpower_path = os.path.join(path, MATPOWER_DIR)
    if not os.path.exists(matpower_path):
        os.mkdir(matpower_path)
    names_path = os.path.join(path, NAMES_DIR)
    if not os.path.exists(names_path):
        os.mkdir(names_path)
    shunts_path = os.path.join(path, SHUNTS_DIR)
    if not os.path.exists(shunts_path):
        os.mkdir(shunts_path)

    # Store a copy
    net = copy.deepcopy(net)

    # Save actual object status
    gen_status = net.gen.in_service.astype(float).values
    ext_grid_status = net.ext_grid.in_service.astype(float).values
    line_status = net.line.in_service.astype(float).values
    trafo_status = net.trafo.in_service.astype(float).values
    ppc_gen_status = np.concatenate([ext_grid_status, gen_status])
    ppc_branch_status = np.concatenate([line_status, trafo_status])

    # Get bus id converter for shunts :
    shunt_id_converter = {v: i for i, v in enumerate(net.bus.index.values)}

    # Set all objects to be in_service and convert to pypower object
    net.gen.in_service = True
    net.ext_grid.in_service = True
    net.line.in_service = True
    net.trafo.in_service = True
    ppc = pp.converter.to_ppc(net, take_slack_vm_limits=False)

    # Manually change the Gen and Branch status to reflect the actual in_service values
    ppc['gen'][:, 7] = ppc_gen_status
    ppc['branch'][:, 10] = ppc_branch_status

    # Get the current step and max step for shunts
    shunts = net.shunt[["bus", "q_mvar", "p_mw", "vn_kv", "max_step", "in_service"]]

    # Modify bus ordering, to account for bus disconnections
    shunts["bus"] = shunts["bus"].map(shunt_id_converter)

    shunts["q_mvar"] = - shunts["q_mvar"]  # Bs = - Q
    shunts.rename(columns={'q_mvar': 'Bs', 'p_mw': 'Gs', 'in_service': 'status'}, inplace=True)

    # Untouched part
    mpc = dict()
    mpc["mpc"] = _ppc2mpc(ppc)

    filepath = os.path.join(matpower_path, net.name + ".m")

    def write_table(f, arr, max_col=None):
        for r in arr:
            for v in r[:max_col]:
                if v.is_integer():
                    f.write("\t{}".format(v.astype(int)))
                else:
                    f.write("\t{:.6f}".format(v))
            f.write(";\n")
        f.write("];\n")

    with open(filepath, "w") as f:
        f.write("function mpc = powergrid\n")
        f.write("mpc.version = '2';\n")
        f.write("mpc.baseMVA = 100;\n")
        f.write("mpc.bus = [\n")
        write_table(f, mpc["mpc"]["bus"], max_col=13)
        f.write("mpc.gen = [\n")
        write_table(f, mpc["mpc"]["gen"], max_col=21)
        f.write("mpc.branch = [\n")
        write_table(f, mpc["mpc"]["branch"], max_col=13)
        f.close()

    # Save names
    names = {
        'bus': list(net.bus.name.astype(str).values),
        'gen': list(net.gen.name.astype(str).values),
        'load': list(net.load.name.astype(str).values),
        'line': list(net.line.name.astype(str).values),
        'trafo': list(net.trafo.name.astype(str).values),
        'ext_grid': list(net.ext_grid.name.astype(str).values),
        'shunt': list(net.shunt.name.astype(str).values),
    }

    names_path = os.path.join(names_path, net.name + ".json")
    with open(names_path, "w") as outfile:
        json.dump(names, outfile)

    shunts_path = os.path.join(shunts_path, net.name + ".csv")
    shunts.to_csv(shunts_path, index=False)

    return None
