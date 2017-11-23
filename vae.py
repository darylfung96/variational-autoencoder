import torch
import torch.nn.functional as F
import torch.nn as nn
from torch.autograd import Variable
import torch.optim as optim
import numpy as np
from tensorflow.examples.tutorials.mnist import input_data

import matplotlib.pyplot as plt


BATCH_SIZE = 64
LATENT_SIZE = 100

""" encoder section """

class Variational_Encoder(nn.Module):

    def __init__(self, input_size, hidden_size):
        super(Variational_Encoder, self).__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.initialize_layers()

    def initialize_layers(self):
        self.first_layer = nn.Linear(self.input_size, self.hidden_size)
        self.second_layer = nn.Linear(self.hidden_size, self.hidden_size)

        self.mean = nn.Linear(self.hidden_size, LATENT_SIZE)
        self.var = nn.Linear(self.hidden_size, LATENT_SIZE)


    def forward(self, x):
        x = F.relu(self.first_layer(x))
        x = F.relu(self.second_layer(x))

        mean = self.mean(x)
        log_var = self.var(x)

        return mean, log_var



# sample from encoder
def sample(mean, log_var):
    eps = Variable(torch.randn((BATCH_SIZE, LATENT_SIZE)))
    return mean + torch.exp(log_var/2) * eps


""" decoder section """
class Variational_decoder(nn.Module):
    def __init__(self, hidden_size, output_size):
        super(Variational_decoder, self).__init__()
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.initialize_layers()

    def initialize_layers(self):
        self.layer1 = nn.Linear(LATENT_SIZE, self.hidden_size)
        self.layer2 = nn.Linear(self.hidden_size, self.hidden_size)
        self.output = nn.Linear(self.hidden_size, self.output_size)

    def forward(self, x):
        x = F.relu(self.layer1(x))
        x = F.relu(self.layer2(x))
        x = F.sigmoid(self.output(x))
        return x


mnist = input_data.read_data_sets('../../MNIST_data', one_hot=True)

encoder = Variational_Encoder(784, 100)
decoder = Variational_decoder(100, 784)

# parameters for the optimizer
params = list(encoder.parameters()) + list(decoder.parameters())
optimizer = optim.Adam(params)


for iteration in range(10000):
    x, _ = mnist.train.next_batch(BATCH_SIZE)
    x_variable = Variable(torch.from_numpy(x))

    mean, log_var = encoder(x_variable)
    x_sample = sample(mean, log_var)
    x_sample = decoder(x_sample)

    recon_loss = F.binary_cross_entropy(x_sample, x_variable, size_average=False) / BATCH_SIZE
    kl_loss = torch.mean( torch.sum(torch.exp(log_var) + mean**2 - 1. - log_var, 1 ) / 2 )

    loss = recon_loss + kl_loss

    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

    if (iteration % 1000 == 0):
        test_true_image = x[0].reshape((28, 28))
        test_sample_image = x_sample.data[0].numpy().reshape((28, 28))
        plot_image = np.concatenate((test_true_image, test_sample_image), axis=1)
        plt.imshow(plot_image)
        plt.show()






