#TODO: Import your dependencies.
#For instance, below are some dependencies you might need if you are using Pytorch
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms
import torch.nn.functional as F

import os
import argparse
from PIL import ImageFile


class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.cnnlayer1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2, 2)
        self.cnnlayer2 = nn.Conv2d(6, 16, 5)
        self.linear1 = nn.Linear(16 * 53 * 53, 256)
        self.linear2 = nn.Linear(256, 84)
        self.linear3 = nn.Linear(84, 5)
                                  

    def forward(self, x):
        x = self.pool(F.relu(self.cnnlayer1(x)))
        x = self.pool(F.relu(self.cnnlayer2(x)))
        x = torch.flatten(x, 1)
        x = F.relu(self.linear1(x))
        x = F.relu(self.linear2(x))
        x = self.linear3(x)
        return x

def test(model, test_loader, criterion, device, args):
    '''
    TODO: Complete this function that can take a model and a 
          testing data loader and will get the test accuray/loss of the model
          Remember to include any debugging/profiling hooks that you might need
    '''
    print("Testing Model on Whole Testing Dataset")
    model.eval()
    running_loss=0
    running_loss_se=0
    running_corrects=0
    
    for inputs, labels in test_loader:
        inputs=inputs.to(device)
        labels=labels.to(device)
        outputs=model(inputs)
        loss=criterion(outputs, labels)
        _, preds = torch.max(outputs, 1)
        running_loss += loss.item() * inputs.size(0)
        running_loss_se += np.square(loss.item() * inputs.size(0))
        running_corrects += torch.sum(preds == labels.data).item()

    total_loss = running_loss / len(test_loader.dataset)
    total_loss_rmse = np.sqrt(running_loss_se / len(test_loader.dataset))
    total_acc = running_corrects/ len(test_loader.dataset)
    print(f"Testing output for Hyperparameters: epoch: {args.epochs}, lr: {args.lr}, batch size: {args.batch_size}, momentum: {args.momentum}")
    print(f"Testing Loss: {total_loss}, Testing RMSE: {total_loss_rmse}, Testing Accuracy: {100*total_acc}")

def train(model, train_loader, validation_loader, criterion, optimizer, device, args):
    '''
    TODO: Complete this function that can take a model and
          data loaders for training and will get train the model
          Remember to include any debugging/profiling hooks that you might need
    '''
    s3 = boto3.resource('s3')
    best_loss=1e6
    image_dataset={'train':train_loader, 'valid':validation_loader}
    loss_counter=0
    print(f"Starting training for Hyperparameters: epoch: {args.epochs}, lr: {args.lr}, batch size: {args.batch_size}, momentum: {args.momentum}")
    train_loss_list = []
    train_acc_list = []
    valid_loss_list = []
    valid_acc_list = []

    for epoch in range(args.epochs):
        for phase in ['train', 'valid']:
            print(f"Epoch {epoch}, Phase {phase}")
            if phase=='train':
                model.train()
            else:
                model.eval()
            running_loss = 0.0
            running_corrects = 0
            running_samples=0

            for step, (inputs, labels) in enumerate(image_dataset[phase]):
                inputs=inputs.to(device)
                labels=labels.to(device)
                outputs = model(inputs)
                loss = criterion(outputs, labels)

                if phase=='train':
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                _, preds = torch.max(outputs, 1)
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data).item()
                running_samples+=len(inputs)
                if running_samples % 2000  == 0:
                    accuracy = running_corrects/running_samples
                    print("Images [{}/{} ({:.0f}%)] Loss: {:.2f} Accuracy: {}/{} ({:.2f}%)".format(
                            running_samples,
                            len(image_dataset[phase].dataset),
                            100.0 * (running_samples / len(image_dataset[phase].dataset)),
                            loss.item(),
                            running_corrects,
                            running_samples,
                            100.0*accuracy,
                        )
                    )
                
                #NOTE: Comment lines below to train and test on whole dataset
                # if running_samples>(0.2*len(image_dataset[phase].dataset)):
                #     break

            epoch_loss = running_loss / running_samples
            epoch_acc = running_corrects / running_samples
            
            if phase=='valid':
                valid_loss_list.append(epoch_loss)
                valid_acc_list.append(epoch_acc)
                if epoch_loss<best_loss:
                    best_loss=epoch_loss
                else:
                    loss_counter+=1
            else:
                train_loss_list.append(epoch_loss)
                train_acc_list.append(epoch_acc)
            
        
        if loss_counter==1:
            break
    return model
    

def create_data_loaders(data, batch_size):
    '''
    This is an optional function that you may or may not need to implement
    depending on whether you need to use data loaders or not
    '''
    transform = transforms.Compose([
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.ToTensor(),
    ])

    dataset = torchvision.datasets.ImageFolder(data, transform=transform)

    data_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size,num_workers=6,
            shuffle=True)

    return data_loader

def save_model(model, model_dir):
    print(f"Saving the model.")
    path = os.path.join(model_dir, "model.pth")
    torch.save(model.cpu().state_dict(), path)

def main(args):
    '''
    TODO: Initialize a model by calling the net function
    '''
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    
    model = Model()
    
    '''
    TODO: Create your loss and optimizer
    '''
    loss_criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)

    '''
    TODO: Call the train function to start training your model
    Remember that you will need to set up a way to get training data from S3
    '''
    train_loader = create_data_loaders(os.environ['SM_CHANNEL_TRAIN'], args.batch_size)
    validation_loader = create_data_loaders(os.environ['SM_CHANNEL_VALID'], args.batch_size)
    test_loader = create_data_loaders(os.environ['SM_CHANNEL_TEST'], args.test_batch_size)
    
    device = torch.device("cuda")
    
    print(f"Training on device: {device}")
    model.to(device)
    
    model=train(model, train_loader, validation_loader, loss_criterion, optimizer, device, args)
    
    '''
    TODO: Test the model to see its accuracy
    '''
    test(model, test_loader, loss_criterion, device, args)
    
    '''
    TODO: Save the trained model
    '''
    save_model(model, args.model_dir)

if __name__=='__main__':
    
    parser=argparse.ArgumentParser()
    '''
    TODO: Specify all the hyperparameters you need to use to train your model.
    '''
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        metavar="N",
        help="input batch size for training (default: 64)",
    )
    parser.add_argument(
        "--test-batch-size",
        type=int,
        default=1000,
        metavar="N",
        help="input batch size for testing (default: 1000)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=5,
        metavar="N",
        help="number of epochs to train (default: 2)",
    )
    parser.add_argument(
        "--lr", type=float, default=1.0, metavar="LR", help="learning rate (default: 1.0)"
    )
   
    parser.add_argument(
        "--momentum", type=float, default=0.9, metavar="N", help="momentum"
    )
    
    # Container environment
    parser.add_argument("--current-host", type=str, default=os.environ["SM_CURRENT_HOST"])
    parser.add_argument("--model-dir", type=str, default=os.environ["SM_MODEL_DIR"])
    parser.add_argument("--num-gpus", type=int, default=os.environ["SM_NUM_GPUS"])
    
    args=parser.parse_args()
    
    main(args)

    

