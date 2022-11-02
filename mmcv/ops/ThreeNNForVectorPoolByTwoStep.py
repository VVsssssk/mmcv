from typing import Tuple

import torch
from torch.autograd import Function

from ..utils import ext_loader

ext_module = ext_loader.load_ext(
    '_ext',
    ['stack_query_local_neighbor_idxs', 'stack_query_three_nn_local_idxs'])


class ThreeNNVectorPoolByTwoStep(Function):
    """The local space around a center point is divided into dense voxels,
    where the inside point-wise features are generated by interpolating from
    three nearest neighbors."""

    @staticmethod
    def forward(
        ctx, xyz: torch.Tensor, xyz_batch_cnt: torch.Tensor,
        new_xyz: torch.Tensor, new_xyz_grid_centers: torch.Tensor,
        new_xyz_batch_cnt: torch.Tensor, max_neighbour_distance: float,
        nsample: int, neighbor_type: int, avg_length_of_neighbor_idxs: int,
        num_total_grids: int, neighbor_distance_multiplier: float
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            xyz (torch.Tensor): XYZ coordinates of the features shape
                with (N1 + N2 ..., 3).
            xyz_batch_cnt: (batch_size): Stacked input xyz coordinates nums in
                each batch, just like (N1, N2, ...).
            new_xyz (torch.Tensor): Centers of the ball
                query shape with (M1 + M2 ..., 3).
            new_xyz_grid_centers (torch.Tensor): Grids centers of each grid
                shape with (M1 + M2 ..., num_total_grids, 3).
            new_xyz_batch_cnt: (batch_size): Stacked centers coordinates
                nums in each batch, just line (M1, M2, ...).
            max_neighbour_distance (float): Max neighbour distance for center.
            nsample (int): Find all (-1), find limited number(>0).
            neighbor_type (int): Neighbor type, 1: ball, others: cube.
            avg_length_of_neighbor_idxs (int): Num avg length of neighbor idxs.
            num_total_grids (int): Total grids num.
            neighbor_distance_multiplier (float): Used to compute
                query_distance. query_distance = neighbor_distance_multiplier
                * max_neighbour_distance

            Returns:
                - new_xyz_grid_dist (torch.Tensor): Three nn xyz for query
                    shape with (M1 + M2 ..., num_total_grids, 3)
                - new_xyz_grid_idxs (torch.Tensor): Indexes for new xyz grids
                    with shape (M1 + M2 ..., num_total_grids, 3).
                - avg_length_of_neighbor_idxs (torch.Tensor): Average length of
                    neighbor indexes.
        """
        num_new_xyz = new_xyz.shape[0]
        new_xyz_grid_dist2 = new_xyz_grid_centers.new_zeros(
            new_xyz_grid_centers.shape)
        new_xyz_grid_idxs = new_xyz_grid_centers.new_zeros(
            new_xyz_grid_centers.shape).int().fill_(-1)

        while True:
            num_max_sum_points = avg_length_of_neighbor_idxs * num_new_xyz
            stack_neighbor_idxs = new_xyz_grid_idxs.new_zeros(
                num_max_sum_points)
            start_len = new_xyz_grid_idxs.new_zeros(num_new_xyz, 2).int()
            cumsum = new_xyz_grid_idxs.new_zeros(1)

            ext_module.stack_query_local_neighbor_idxs(
                xyz.contiguous(), xyz_batch_cnt.contiguous(),
                new_xyz.contiguous(), new_xyz_batch_cnt.contiguous(),
                stack_neighbor_idxs.contiguous(), start_len.contiguous(),
                cumsum, avg_length_of_neighbor_idxs,
                max_neighbour_distance * neighbor_distance_multiplier, nsample,
                neighbor_type)
            avg_length_of_neighbor_idxs = cumsum[0].item(
            ) // num_new_xyz + int(cumsum[0].item() % num_new_xyz > 0)

            if cumsum[0] <= num_max_sum_points:
                break

        stack_neighbor_idxs = stack_neighbor_idxs[:cumsum[0]]
        ext_module.stack_query_three_nn_local_idxs(
            xyz, new_xyz, new_xyz_grid_centers, new_xyz_grid_idxs,
            new_xyz_grid_dist2, stack_neighbor_idxs, start_len, num_new_xyz,
            num_total_grids)

        return torch.sqrt(new_xyz_grid_dist2), new_xyz_grid_idxs, torch.tensor(
            avg_length_of_neighbor_idxs)


three_nn_vector_pool_by_two_step = ThreeNNVectorPoolByTwoStep.apply
