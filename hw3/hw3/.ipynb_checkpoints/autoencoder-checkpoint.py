import torch
import torch.nn as nn
import torch.nn.functional as F
import math

class EncoderCNN(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()

        modules = []

        # TODO:
        #  Implement a CNN. Save the layers in the modules list.
        #  The input shape is an image batch: (N, in_channels, H_in, W_in).
        #  The output shape should be (N, out_channels, H_out, W_out).
        #  You can assume H_in, W_in >= 64.
        #  Architecture is up to you, but it's recommended to use at
        #  least 3 conv layers. You can use any Conv layer parameters,
        #  use pooling or only strides, use any activation functions,
        #  use BN or Dropout, etc.
        # ====== YOUR CODE: ======
        channels = [in_channels, 32, 64, 128, out_channels]
        kernel_size = 5
        for in_c, out_c in zip(channels[:-1], channels[1:]):
            modules.append(nn.Conv2d(in_c, out_c, kernel_size=kernel_size , bias=False))
            modules.append(nn.BatchNorm2d(out_c))
            modules.append(nn.ReLU())
        # ========================
        self.cnn = nn.Sequential(*modules)

    def forward(self, x):
        return self.cnn(x)


class DecoderCNN(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()

        modules = []

        # TODO:
        #  Implement the "mirror" CNN of the encoder.
        #  For example, instead of Conv layers use transposed convolutions,
        #  instead of pooling do unpooling (if relevant) and so on.
        #  The architecture does not have to exactly mirror the encoder
        #  (although you can), however the important thing is that the
        #  output should be a batch of images, with same dimensions as the
        #  inputs to the Encoder were.
        # ====== YOUR CODE: ======
        channels = [in_channels, 128, 64, 32, out_channels]
        kernel_size = 5
        for in_c, out_c in zip(channels[:-1], channels[1:]):
            modules.append(nn.ConvTranspose2d(in_c, out_c, kernel_size=kernel_size, bias=False))
            if out_c != out_channels:
                modules.append(nn.BatchNorm2d(out_c))
                modules.append(nn.ReLU())
        # ========================
        self.cnn = nn.Sequential(*modules)

    def forward(self, h):
        # Tanh to scale to [-1, 1] (same dynamic range as original images).
        return torch.tanh(self.cnn(h))


class VAE(nn.Module):
    def __init__(self, features_encoder, features_decoder, in_size, z_dim):
        """
        :param features_encoder: Instance of an encoder the extracts features
        from an input.
        :param features_decoder: Instance of a decoder that reconstructs an
        input from it's features.
        :param in_size: The size of one input (without batch dimension).
        :param z_dim: The latent space dimension.
        """
        super().__init__()
        self.features_encoder = features_encoder
        self.features_decoder = features_decoder
        self.z_dim = z_dim

        self.features_shape, n_features = self._check_features(in_size)

        # TODO: Add more layers as needed for encode() and decode().
        # ====== YOUR CODE: ======
        device = next(self.parameters()).device
        self.layer_var_log = nn.Linear(n_features, z_dim).to(device)
        self.layer_mean = nn.Linear(n_features, z_dim).to(device)
        self.layer_from_z = nn.Linear(z_dim, n_features).to(device)
        # ========================

    def _check_features(self, in_size):
        device = next(self.parameters()).device
        with torch.no_grad():
            # Make sure encoder and decoder are compatible
            x = torch.randn(1, *in_size, device=device)
            h = self.features_encoder(x)
            xr = self.features_decoder(h)
            assert xr.shape == x.shape
            # Return the shape and number of encoded features
            return h.shape[1:], torch.numel(h) // h.shape[0]

    def encode(self, x):
        # TODO:
        #  Sample a latent vector z given an input x from the posterior q(Z|x).
        #  1. Use the features extracted from the input to obtain mu and
        #     log_sigma2 (mean and log variance) of q(Z|x).
        #  2. Apply the reparametrization trick to obtain z.
        # ====== YOUR CODE: ======
        device = next(self.parameters()).device
        features = self.features_encoder(x.to(device)).view((x.shape[0], -1))
        mu = self.layer_mean(features)
        log_sigma2 = self.layer_var_log(features)
        z = mu + torch.randn_like(mu, device=device) * torch.sqrt(torch.exp(log_sigma2))
        # ========================

        return z, mu, log_sigma2

    def decode(self, z):
        # TODO:
        #  Convert a latent vector back into a reconstructed input.
        #  1. Convert latent z to features h with a linear layer.
        #  2. Apply features decoder.
        # ====== YOUR CODE: ======
        device = next(self.parameters()).device
        features = self.layer_from_z(z.to(device)).view((-1, *self.features_shape))
        x_rec = self.features_decoder(features)
        # ========================

        # Scale to [-1, 1] (same dynamic range as original images).
        return torch.tanh(x_rec)

    def sample(self, n):
        samples = []
        device = next(self.parameters()).device
        with torch.no_grad():
            # TODO:
            #  Sample from the model. Generate n latent space samples and
            #  return their reconstructions.
            #  Notes:
            #  - Remember that this means using the model for INFERENCE.
            #  - We'll ignore the sigma2 parameter here:
            #    Instead of sampling from N(psi(z), sigma2 I), we'll just take
            #    the mean, i.e. psi(z).
            # ====== YOUR CODE: ======
            latent_sampels = torch.randn(n, self.z_dim).to(device)
            samples = self.decode(latent_sampels).to(device)
            # ========================

        # Detach and move to CPU for display purposes
        samples = [s.detach().cpu() for s in samples]
        return samples

    def forward(self, x):
        z, mu, log_sigma2 = self.encode(x)
        return self.decode(z), mu, log_sigma2


def vae_loss(x, xr, z_mu, z_log_sigma2, x_sigma2):
    """
    Point-wise loss function of a VAE with latent space of dimension z_dim.
    :param x: Input image batch of shape (N,C,H,W).
    :param xr: Reconstructed (output) image batch.
    :param z_mu: Posterior mean (batch) of shape (N, z_dim).
    :param z_log_sigma2: Posterior log-variance (batch) of shape (N, z_dim).
    :param x_sigma2: Likelihood variance (scalar).
    :return:
        - The VAE loss
        - The data loss term
        - The KL divergence loss term
    all three are scalars, averaged over the batch dimension.
    """
    loss, data_loss, kldiv_loss = None, None, None
    # TODO:
    #  Implement the VAE pointwise loss calculation.
    #  Remember:
    #  1. The covariance matrix of the posterior is diagonal.
    #  2. You need to average over the batch dimension.
    # ====== YOUR CODE: ======
    x_dim = torch.numel(torch.FloatTensor(x.shape))
    batch_dim = x.shape[0]
    z_dim = z_mu.shape[1]
    divide_factor = x_sigma2 * x_dim

    data_loss = torch.pow(((x - xr).norm()), 2) / divide_factor

    trace = torch.sum(torch.exp(z_log_sigma2))
    norm2_z_mu = torch.pow(torch.norm(z_mu), 2)
    det_log = torch.sum(z_log_sigma2)
    kldiv_loss = (trace + norm2_z_mu - det_log) / batch_dim - z_dim

    loss = data_loss + kldiv_loss
    # ========================

    return loss, data_loss, kldiv_loss
