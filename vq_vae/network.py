import torch
import torch.nn as nn
import torch.nn.functional as F


class Residual(nn.Module):
    def __init__(self, input_channels, residual_units):
        super(Residual, self).__init__()
        self._block = nn.Sequential(
            nn.ReLU(True),
            nn.Conv2d(in_channels=input_channels,
                      out_channels=residual_units,
                      kernel_size=3, stride=1, padding=1, bias=False),
            nn.ReLU(True),
            nn.Conv2d(in_channels=residual_units,
                      out_channels=input_channels,  # For residual
                      kernel_size=1, stride=1, bias=False)
        )

    def forward(self, inputs):
        return inputs + self._block(inputs)


class VectorQuantize(nn.Module):
    def __init__(self, num_embeddings, embeddings_dim, commitment_cost):
        super(VectorQuantize, self).__init__()
        self.num_embeddings = num_embeddings
        self.embeddings_dim = embeddings_dim
        self.commitment_cost = commitment_cost

        self.embeddings = nn.Embedding(num_embeddings, embeddings_dim)
        self.embeddings.weight.data.uniform_(-1/self.num_embeddings, 1/self.num_embeddings)

    def forward(self, inputs):
        flatten_inputs = inputs.view(-1, self.embeddings_dim)
        # find the nearest neighbour from the inputs to the embedding table
        distance = torch.sum(flatten_inputs**2, dim=1, keepdim=True) + \
                   torch.sum(self.embeddings.weight**2, dim=1) - \
                   2 * torch.matmul(flatten_inputs, self.embeddings.weight.t())

        selected_e_index = torch.argmin(distance, dim=1).unsqueeze(1)
        one_hot_e_index = torch.zeros(selected_e_index.shape[0], self.num_embeddings)
        one_hot_e_index.scatter_(1, selected_e_index, 1)

        e = torch.matmul(one_hot_e_index, self.embeddings.weight).view(inputs.shape)

        # find loss
        # e_loss (commitment loss is to control how much the latent produced from the encoder to
        # not deviate that much from the codebook)
        e_loss = torch.mean((e.detach() - inputs) ** 2)
        q_loss = torch.mean((inputs.detach() - e) ** 2)
        loss = self.commitment_cost * e_loss + q_loss

        # calculate the latent as the original z(output of encoder) in addition with the change from the
        # original z to the selected e (codebook)
        # this cause the latent to not diverge that much from the codebook
        latent = inputs + (e - inputs).detach()
        return loss, latent


class Encoder(nn.Module):
    def __init__(self, in_channels, hidden_units, num_layers, residual_hidden_units, number_pre_conv):
        super(Encoder, self).__init__()

        assert number_pre_conv == 2 or number_pre_conv == 4

        if number_pre_conv == 4:
            layer_modules = [
                nn.Conv2d(in_channels=in_channels,
                          out_channels=hidden_units//2,
                          kernel_size=4,
                          stride=2, padding=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(in_channels=hidden_units // 2,
                          out_channels=hidden_units,
                          kernel_size=4,
                          stride=2, padding=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(in_channels=hidden_units,
                          out_channels=hidden_units,
                          kernel_size=3,
                          stride=1, padding=1)

            ]
        elif number_pre_conv == 2:
            layer_modules = [
                nn.Conv2d(in_channels=hidden_units // 2,
                          out_channels=hidden_units,
                          kernel_size=4,
                          stride=2, padding=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(in_channels=hidden_units,
                          out_channels=hidden_units,
                          kernel_size=3,
                          stride=1, padding=1)
            ]

        for i in range(num_layers):
            layer_modules.append(Residual(hidden_units, residual_hidden_units) for i in range(num_layers))
        layer_modules.append(nn.ReLU(inplace=True))

        self.layers = nn.Sequential(*layer_modules)

    def forward(self, inputs):
        return self.layers


class Decoder(nn.Module):
    def __init__(self, in_channels, hidden_units, num_layers, residual_hidden_units, number_post_trans_conv):
        super(Decoder, self).__init__()
        self._1_de_conv = nn.Conv2d(in_channels=in_channels,
                                    out_channels=hidden_units,
                                    kernel_size=3,
                                    stride=1, padding=1)

        layer_lists = [Residual(hidden_units, residual_hidden_units) for _ in range(num_layers)]
        self.residual_layers = nn.Sequential(*layer_lists)

        if number_post_trans_conv == 2:
            post_layers_modules = [
                nn.ConvTranspose2d(in_channels=hidden_units,
                                   out_channels=hidden_units//2,
                                   kernel_size=4,
                                   stride=2, padding=1),
                nn.ReLU(inplace=True),
                nn.ConvTranspose2d(in_channels=hidden_units // 2,
                                   out_channels=3,
                                   kernel_size=4,
                                   stride=2, padding=1)
            ]
        elif number_post_trans_conv == 1:
            post_layers_modules = [
                nn.ConvTranspose2d(in_channels=hidden_units,
                                   out_channels=3,
                                   kernel_size=4,
                                   stride=2, padding=1)
            ]

        self.post_block = nn.Sequential(*post_layers_modules)

    def forward(self, inputs):
        x = self._1_de_conv(inputs)
        x = self.residual_layers(x)
        return self.post_block(x)


class Model(nn.Module):
    def __init__(self, hidden_units, residual_layers, residual_hidden_units, num_embeddings, embeddings_dim,
                 commitment_cost):
        super(Model, self).__init__()

        self._encoder = Encoder(3, hidden_units, residual_layers, residual_hidden_units)
        self._before_z = nn.Conv2d(in_channels=hidden_units, out_channels=embeddings_dim, kernel_size=1, stride=1)
        self._vq = VectorQuantize(num_embeddings, embeddings_dim, commitment_cost)
        self._decoder = Decoder(embeddings_dim, hidden_units, residual_layers, residual_hidden_units)

    def forward(self, inputs):
        x = self._encoder(inputs)
        x = self._before_z(x)
        loss, x = self._vq(x)
        recon_x = self._decoder(x)
        return loss, recon_x

