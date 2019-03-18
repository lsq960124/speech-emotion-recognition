import torch
import os
from time import gmtime, strftime
import json

from models import RNN
from model_ops import evaluate, train
from batch_iterator import BatchIterator
from data_loader import get_transcription_embeddings_and_labels
from utils import timeit, log, log_major, log_success
from config import Config


MODEL_PATH = "saved_models"
TRANSCRIPTIONS_VAL_PATH = "data/iemocap_transcriptions_val.json"
TRANSCRIPTIONS_TRAIN_PATH = "data/iemocap_transcriptions_train.json"


@timeit
def run_training(cfg):
    model_run_path = MODEL_PATH + "/" + strftime("%Y-%m-%d_%H:%M:%S", gmtime())
    model_weights_path = "{}/model.torch".format(model_run_path)
    model_config_path = "{}/config.json".format(model_run_path)
    result_path = "{}/result.txt".format(model_run_path)
    os.makedirs(model_run_path, exist_ok=True)

    """Choosing hardware"""
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == "cuda":
        torch.set_default_tensor_type('torch.cuda.FloatTensor')
    else:
        torch.set_default_tensor_type('torch.FloatTensor')

    json.dump(cfg.to_json(), open(model_config_path, "w"))

    """Converting model to specified hardware and format"""
    model = RNN(cfg)
    model.float()
    model = model.to(device)

    """Defining loss and optimizer"""
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.lr)
    criterion = torch.nn.CrossEntropyLoss()
    criterion = criterion.to(device)

    """Loading data"""
    val_transcriptions, val_labels = get_transcription_embeddings_and_labels(TRANSCRIPTIONS_VAL_PATH, cfg.seq_len)
    train_transcriptions, train_labels = get_transcription_embeddings_and_labels(TRANSCRIPTIONS_TRAIN_PATH, cfg.seq_len)

    """Creating data generators"""
    train_iterator = BatchIterator(train_transcriptions, train_labels, cfg.batch_size)
    validation_iterator = BatchIterator(val_transcriptions, val_labels, 100)

    train_loss = 999
    best_valid_loss = 999
    train_acc = None
    epochs_without_improvement = 0

    """Running training"""
    for epoch in range(cfg.n_epochs):
        train_iterator.shuffle()
        if epochs_without_improvement == cfg.patience:
            break

        valid_loss, valid_acc, conf_mat = evaluate(model, validation_iterator, criterion)

        if valid_loss < best_valid_loss:
            torch.save(model.state_dict(), model_weights_path)
            best_valid_loss = valid_loss
            best_valid_acc = valid_acc
            best_conf_mat = conf_mat
            epochs_without_improvement = 0
            log_success(" Epoch: {} | Val loss improved to {:.4f} | val acc: {:.3f} | train loss: {:.4f} | train acc: {:.3f} | saved model to {}.".format(
                epoch, best_valid_loss, best_valid_acc, train_loss, train_acc, model_weights_path
            ))

        train_loss, train_acc = train(model, train_iterator, optimizer, criterion, cfg.reg_ratio)

        epochs_without_improvement += 1
    
        if not epoch % 1:
            log(f'| Epoch: {epoch+1} | Val Loss: {valid_loss:.3f} | Val Acc: {valid_acc*100:.2f}% '
                f'| Train Loss: {train_loss:.4f} | Train Acc: {train_acc*100:.3f}%', cfg.verbose)

    result = f'| Epoch: {epoch+1} | Val Loss: {best_valid_loss:.3f} | Val Acc: {best_valid_acc*100:.2f}% | ' \
             f'Train Loss: {train_loss:.4f} | Train Acc: {train_acc*100:.3f}% \n Confusion matrix:\n {best_conf_mat}'
    log_major(result)
    log_major("Hyperparameters:{}".format(cfg.to_json()))
    with open(result_path, "w") as file:
        file.write(result)


if __name__ == "__main__":
    run_training(Config())
