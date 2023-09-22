import argparse
import tqdm
import os

import pandapower as pp
from converter import to_mpc


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Convert a database into a target format.')
    parser.add_argument('dataset', type=str,
                        help='Path to the database (which contains train/ and test/) which you want to convert')
    args = parser.parse_args()

    source_path = args.dataset
    target_path = source_path + '_matpower'
    os.mkdir(target_path)
    for source_file in tqdm.tqdm(os.listdir(source_path)):
        if source_file.endswith('.json'):
            #try:
            net = pp.from_json(os.path.join(source_path, source_file))
            net.name = os.path.splitext(os.path.basename(source_file))[0]
            to_mpc(net, target_path)
            #except:
            #    print("{} is not a valid pandapower file.".format(source_file))
        else:
            pass
