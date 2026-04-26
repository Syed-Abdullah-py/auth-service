import argparse
import numpy as np
import nibabel as nib
import os

# Suppress TensorFlow logs for cleaner output
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf
from keras.models import load_model
import keras.backend as K

def standardize(image):
    standardized_image = np.zeros(image.shape)
    for z in range(image.shape[2]):
        image_slice = image[:,:,z]
        centered = image_slice - np.mean(image_slice)
        if(np.std(centered)!=0):
            centered = centered/np.std(centered) 
        standardized_image[:, :, z] = centered
    return standardized_image

def dice_coef(y_true, y_pred, epsilon=0.00001):
    axis = (0,1,2,3)
    dice_numerator = 2. * K.sum(y_true * y_pred, axis=axis) + epsilon
    dice_denominator = K.sum(y_true*y_true, axis=axis) + K.sum(y_pred*y_pred, axis=axis) + epsilon
    return K.mean((dice_numerator)/(dice_denominator))

def dice_coef_loss(y_true, y_pred):
    return 1-dice_coef(y_true, y_pred)

def main():
    parser = argparse.ArgumentParser(description='Run 3D U-Net Inference on BraTS modalities.')
    parser.add_argument('--flair', required=True, help='Path to FLAIR modality (.nii.gz)')
    parser.add_argument('--t1', required=True, help='Path to T1 modality (.nii.gz)')
    parser.add_argument('--t1ce', required=True, help='Path to T1ce modality (.nii.gz)')
    parser.add_argument('--t2', required=True, help='Path to T2 modality (.nii.gz)')
    parser.add_argument('--output', required=True, help='Path to save output mask (.nii.gz)')
    parser.add_argument('--model', default='brats_3d_model_11epochs.h5', help='Path to trained model')

    args = parser.parse_args()

    print(f"Loading model from {args.model}...")
    model = load_model(args.model, custom_objects={'dice_coef_loss': dice_coef_loss, 'dice_coef': dice_coef})

    print("Loading and standardizing input modalities...")
    data = np.zeros((240, 240, 155, 4))
    
    # Order of modalities MUST match the order used during training.
    # In 3d_Unet_results.py: "modalities.sort()" -> flair, t1, t1ce, t2.
    modalities = [args.flair, args.t1, args.t1ce, args.t2]
    ref_affine = None

    for idx, path in enumerate(modalities):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        img = nib.load(path)
        if ref_affine is None:
            ref_affine = img.affine
            
        # We use get_fdata() which is standard in nibabel
        image_data = img.get_fdata() 
        image_data = np.asarray(image_data)
        data[:, :, :, idx] = standardize(image_data)
        print(f"  Processed {path}")

    print("Running prediction...")
    # Crop data as expected by the model
    reshaped_data = data[56:184, 75:203, 13:141, :]
    reshaped_data = reshaped_data.reshape(1, 128, 128, 128, 4)

    Y_hat = model.predict(x=reshaped_data)
    Y_hat = np.argmax(Y_hat, axis=-1)
    
    # Y_hat is shape (1, 128, 128, 128), squeeze the batch dimension
    Y_hat = np.squeeze(Y_hat, axis=0)

    print("Reconstructing full-size mask...")
    full_mask = np.zeros((240, 240, 155), dtype=np.uint8)
    full_mask[56:184, 75:203, 13:141] = Y_hat

    # Note: During training, class 4 was mapped to 3 (reshaped_image_data2[reshaped_image_data2==4] = 3).
    # BraTS labels: 1=Necrotic/Non-Enhancing Core, 2=Edema, 4=Enhancing Tumor.
    # Re-mapping 3 back to 4 to match official BraTS format.
    full_mask[full_mask == 3] = 4

    print(f"Saving output to {args.output}...")
    out_img = nib.Nifti1Image(full_mask, ref_affine)
    nib.save(out_img, args.output)
    print("Done!")

if __name__ == '__main__':
    main()
