import torch
import torch.nn as nn
from survae.transforms import Bijection

from ..flows.mixture_cdf_layer import MixtureCDFCoupling


class CouplingMixtureCDFCoupling(Bijection):

	def __init__(self, c_in, c_out, model_func, block_type=None, num_mixtures=10):
		super().__init__()
		self.c_in = c_in
		self.c_out = c_out
		self.num_mixtures = num_mixtures
		self.block_type = block_type
		self.scaling_factor = nn.Parameter(torch.zeros(self.c_out))
		self.mixture_scaling_factor = nn.Parameter(torch.zeros(self.c_out, self.num_mixtures))
		self.nn = model_func(c_in=c_in, c_out=c_out*(2 + 3 * self.num_mixtures))

	def forward(self, z, reverse=False, **kwargs):
		ldj = z.new_zeros(z.size(0),)

		kwargs['length'] = z.new_ones(size=(z.size(0),)).int() * z.size(2)

		z = z.permute(0, 2, 1)

		id, z = torch.split(z, (self.c_in, self.c_out), dim=-1)

		if not reverse:
			nn_out = self.nn(x=id, **kwargs)

			t, log_s, log_pi, mixt_t, mixt_log_s = MixtureCDFCoupling.get_mixt_params(nn_out, mask=None,
																				 num_mixtures=self.num_mixtures,
																				 scaling_factor=self.scaling_factor,
																				 mixture_scaling_factor=self.mixture_scaling_factor)

			z = z.double()
			z_out, ldj_mixt = MixtureCDFCoupling.run_with_params(z, t, log_s, log_pi, mixt_t, mixt_log_s, reverse=reverse)
		else:
			# Note: even comment out next line, the model still cannot backprop
			with torch.no_grad():
				nn_out = self.nn(x=id, **kwargs)
				t, log_s, log_pi, mixt_t, mixt_log_s = MixtureCDFCoupling.get_mixt_params(nn_out, mask=None,
																					 num_mixtures=self.num_mixtures,
																					 scaling_factor=self.scaling_factor,
																					 mixture_scaling_factor=self.mixture_scaling_factor)
				z = z.double()
				z_out, ldj_mixt = MixtureCDFCoupling.run_with_params(z, t, log_s, log_pi, mixt_t, mixt_log_s, reverse=reverse)

		ldj = ldj + ldj_mixt.float()
		z_out = z_out.float()
		if "channel_padding_mask" in kwargs and kwargs["channel_padding_mask"] is not None:
			z_out = z_out * kwargs["channel_padding_mask"]

		z_out = torch.cat([id, z_out], dim=-1)
		z_out = z_out.permute(0, 2, 1)

		if reverse:
			return z_out

		return z_out, ldj

	def inverse(self, z):
		return self.forward(z, reverse=True)

	def info(self):
		s = "Autoregressive Mixture CDF Coupling Layer - Input size %i" % (self.c_in)
		if self.block_type is not None:
			s += ", block type %s" % (self.block_type)
		return s
