import argparse
import tqdm
import os

import pandapower as pp
from converter import from_mpc, MATPOWER_DIR


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Convert a database into a target format.')
    parser.add_argument('dataset', type=str,
                        help='Path to the database (which contains train/ and test/) which you want to convert')
    args = parser.parse_args()

    source_path = args.dataset
    target_path = source_path + '_pandapower'
    os.mkdir(target_path)
    for source_file in tqdm.tqdm(os.listdir(os.path.join(source_path, MATPOWER_DIR))):
        if source_file.endswith('.m'):
            file_path = os.path.join(os.path.join(source_path, MATPOWER_DIR), source_file)
            net = from_mpc(file_path)
            pp.to_json(net, os.path.join(target_path, net.name)+'.json')
        else:
            pass
