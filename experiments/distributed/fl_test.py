import argparse
import logging
import os
import sys

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import wandb
import joblib
from matplotlib import pyplot as plt

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../")))

from model.ae import AutoEncoder

def add_args(parser):
    """
    parser : argparse.ArgumentParser
    return a parser added with args required by fit
    """
    # dataset related
    parser.add_argument('--dataset', type=str, default='UCI_MLR', metavar='N',
                        help='dataset used for training')

    parser.add_argument('--data_dir', type=str, default='./../../data/UCI-MLR',
                        help='data directory')

    # CPU/GPU device related
    parser.add_argument('--device', type=str, default='cpu',
                        help='cpu; gpu')

    # model related
    parser.add_argument('--model', type=str, default='vae',
                        help='model (default: vae): ae, vae')

    # optimizer related
    parser.add_argument('--batch_size', type=int, default=32, metavar='N',
                        help='input batch size for training (default: 64)')

    parser.add_argument('--client_optimizer', type=str, default='adam',
                        help='SGD with momentum; adam')

    parser.add_argument('--lr', type=float, default=0.001, metavar='LR',
                        help='learning rate (default: 0.001)')

    parser.add_argument('--wd', help='weight decay parameter;', type=float, default=0.001)

    parser.add_argument('--epochs', type=int, default=50, metavar='EP',
                        help='how many epochs will be trained')

    args = parser.parse_args()
    return args

# for global test
def load_data(args):

    path_test_traffic = args.data_dir + '/new_centralized_set/global_testset.csv'
    logging.info(path_test_traffic)

    db_test = pd.read_csv(path_test_traffic)
    db_test = (db_test - db_test.mean()) / (db_test.std())
    db_test[np.isnan(db_test)] = 0
    testset = np.array(db_test)
    test_tr = 9000
    test_benign = testset[8000:9000]
    test_anmoaly = testset[14400:15200]
    benignloader = torch.utils.data.DataLoader(test_benign, batch_size=1, shuffle=False, num_workers=0)
    anloader = torch.utils.data.DataLoader(test_anmoaly, batch_size=1, shuffle=False, num_workers=0)
    return benignloader, anloader, len(testset), test_tr

#for local test
# def load_data(args):
#
#     path_benin_traffic = args.data_dir + '/Philips_B120N10_Baby_Monitor/benign_traffic.csv'
#     path_test_traffic = args.data_dir + '/Philips_B120N10_Baby_Monitor/Philips_Baby_Monitor_test_raw.csv'
#     logging.info(path_test_traffic)
#
#     db_benign = pd.read_csv(path_benin_traffic)
#     db_test = pd.read_csv(path_test_traffic)
#     db_test = (db_test - db_test.mean()) / (db_test.std())
#     db_benign = (db_benign - db_benign.mean()) / (db_benign.std())
#     db_benign[np.isnan(db_benign)] = 0
#     db_test[np.isnan(db_test)] = 0
#
#     trainset = db_benign[0:round(len(db_benign) * 0.67)]
#     trainset = np.array(trainset)
#     testset = np.array(db_test)
#     test_tr = 9000
#     test_benign = trainset[0:1000]
#     test_anmoaly = testset[0:800]
#     benignloader = torch.utils.data.DataLoader(test_benign, batch_size=1, shuffle=False, num_workers=0)
#     anloader = torch.utils.data.DataLoader(test_anmoaly, batch_size=1, shuffle=False, num_workers=0)
#     return benignloader, anloader, len(testset), test_tr



def create_model(args):
    model = AutoEncoder()
    model_save_dir = "/Users/ultraz/PycharmProjects/FedML-IoT-V/experiments/distributed"
    path = os.path.join(model_save_dir, 'model.ckpt')
    model.load_state_dict(torch.load(path, map_location=lambda storage, loc: storage))
    return model


def test(args, model, device, benignloader, anloader, threshold):
    model.eval()
    true_negative = []
    false_positive = []
    true_positive = []
    false_negative = []

    thres_func = nn.MSELoss()
    for idx, inp in enumerate(benignloader):
        inp = inp.to(device)
        diff = thres_func(model(inp), inp)
        mse = diff.item()
        if mse > threshold:
            false_positive.append(idx)
        else:
            true_negative.append(idx)

    for idx, inp in enumerate(anloader):
        inp = inp.to(device)
        diff = thres_func(model(inp), inp)
        mse = diff.item()
        if mse > threshold:
            true_positive.append(idx)
        else:
            false_negative.append(idx)


    accuracy = (len(true_positive) + len(true_negative)) \
                / (len(true_positive) + len(true_negative) + len(false_positive) + len(false_negative))
    precision = len(true_positive) / (len(true_positive) + len(false_positive))
    false_positive_rate = len(false_positive) / (len(false_positive) + len(true_negative))

    print('The True negative number is ', len(true_negative))
    print('The False positive number is ', len(false_positive))
    print('The True positive number is ', len(true_positive))
    print('The False negative number is ', len(false_negative))

    print('The accuracy is ', accuracy)
    print('The precision is ', precision)
    print('The false positive rate is ', false_positive_rate)

    wandb.log({"accuracy": accuracy})
    wandb.log({"precision": precision})
    wandb.log({"false positive rate": false_positive_rate})

    return accuracy, precision, false_positive_rate

if __name__ == "__main__":
    # logging.basicConfig(level=logging.INFO,

    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                        datefmt='%a, %d %b %Y %H:%M:%S')

    # parse python script input parameters
    parser = argparse.ArgumentParser()
    args = add_args(parser)
    logging.info(args)

    # experimental result tracking
    wandb.init(project='fediot', entity='automl', config=args)

    # PyTorch configuration
    torch.set_default_tensor_type(torch.DoubleTensor)

    # GPU/CPU device management
    if args.device == "gpu":
        device = torch.device("cuda:0")
    else:
        device = torch.device("cpu")

    # load data
    benignloader, anloader, test_len, test_tr = load_data(args)

    # create model
    model = create_model(args)

    threshold_dict = joblib.load("/Users/ultraz/PycharmProjects/FedML-IoT-V/experiments/distributed/threshold_dict.pkl")

    acc, pre, fprate = test(args, model, device, benignloader, anloader, threshold_dict[8])
    # accuracy = []
    # precision = []
    # fpr = []
    # start test
    # for i in range(9):
    #     acc, pre, fprate = test(args, model, device, benignloader, anloader, threshold_dict[i])
    #     accuracy.append(acc)
    #     precision.append(pre)
    #     fpr.append(fprate)
    # fl2_acc = np.mean(accuracy)
    # fl2_pre = np.mean(precision)
    # fl2_fpr = np.mean(fpr)
    # print("The final result is: ",fl2_acc,fl2_pre,fl2_fpr)